"""
seo_assembler.py — Confidence scoring, JSON-LD rendering, and final output assembly.

Responsibilities:
1. Compute confidence score (6-signal heuristic quality gate)
2. Render NewsArticle and FAQPage JSON-LD schemas via Jinja2
3. Assemble the final FinalArticleJSON output dict
4. Write JSON files to the output directory
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

import config
from config import (
    OUTPUT_DIR, SEO_TEMPLATES_DIR,
    CONFIDENCE_AUTO_PUBLISH, CONFIDENCE_REVIEW_REQUIRED,
    PRICE_ANOMALY_THRESHOLD_PCT, MIN_WORD_COUNT, MAX_WORD_COUNT,
    VALID_TRANSLATION_LENGTH_RATIO,
)
from schemas import (
    AnalyticsPayload, ArticleDraft, ArticleOutput, FAQItem, FinalArticleJSON, MarketRow,
    ScopeTarget, TranslatedArticle
)
from translator import check_numeric_integrity, check_length_ratio

logger = logging.getLogger("mandibhav.seo_assembler")

# Language codes to ISO 639-1 + region tags
LANGUAGE_ISO: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
}

# Jinja2 environment
_jinja_env: Optional[Environment] = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(SEO_TEMPLATES_DIR)),
            autoescape=False,  # We're outputting JSON, not HTML
        )
    return _jinja_env


# ---------------------------------------------------------------------------
# Confidence scoring (6-signal quality gate)
# ---------------------------------------------------------------------------

def _check_output_validity(article: ArticleOutput) -> float:
    """Check word count, HTML presence, and FAQ count."""
    from html.parser import HTMLParser

    class HTMLTagCounter(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)

    # Word count check (strip HTML for word count)
    plain_text = re.sub(r"<[^>]+>", " ", article.body_html)
    word_count = len(plain_text.split())

    if not (MIN_WORD_COUNT <= word_count <= MAX_WORD_COUNT):
        logger.debug("Word count %d outside range [%d, %d]", word_count, MIN_WORD_COUNT, MAX_WORD_COUNT)
        return 0.0

    # HTML structure check
    counter = HTMLTagCounter()
    try:
        counter.feed(article.body_html)
    except Exception:
        return 0.0

    has_headings = any(t in counter.tags for t in ["h2", "h3"])
    has_paragraphs = "p" in counter.tags

    if not (has_headings and has_paragraphs):
        logger.debug("Missing required HTML structure (h2/h3 + p)")
        return 0.0

    # FAQ check
    if len(article.faqs) < 2:
        logger.debug("Insufficient FAQs: %d < 2", len(article.faqs))
        return 0.5  # Partial credit

    return 1.0


def _check_numeric_in_article(article: ArticleOutput, analytics: AnalyticsPayload) -> float:
    """
    Verify that key analytics numbers appear somewhere in the article.
    Checks national_avg_modal and at least one market price.
    """
    body_numbers = set(
        re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", article.body_html.replace(",", ""))
    )

    required_numbers = {str(int(analytics.national_avg_modal))}
    if analytics.markets:
        for m in analytics.markets[:3]:
            required_numbers.add(str(int(m.modal_price)))

    missing = required_numbers - body_numbers
    if missing:
        logger.debug("Missing analytics numbers in article body: %s", missing)
        return 0.0
    return 1.0


def _check_keyword_coverage(article: ArticleOutput, required_keywords: list[str]) -> float:
    """Check what fraction of required keywords appear in the article body or title."""
    if not required_keywords:
        return 1.0
    body_lower = (article.title + " " + article.body_html).lower()
    found = sum(1 for kw in required_keywords if kw.lower() in body_lower)
    return found / len(required_keywords)


def _check_price_anomaly(analytics: AnalyticsPayload) -> float:
    """Flag if day-over-day price change exceeds threshold."""
    if analytics.national_day_change_pct is None:
        return 1.0  # No prev data — cannot flag
    if abs(analytics.national_day_change_pct) > PRICE_ANOMALY_THRESHOLD_PCT:
        logger.warning(
            "Price anomaly detected for %s: %.2f%% change",
            analytics.scope_key, analytics.national_day_change_pct
        )
        return 0.0
    return 1.0


def _check_data_coverage(analytics: AnalyticsPayload) -> float:
    """Check that there are enough reporting markets for this scope."""
    min_markets = 2 if analytics.article_type != "market_spotlight" else 1
    return 1.0 if analytics.market_count >= min_markets else 0.0


def compute_confidence(
    article: ArticleOutput,
    analytics: AnalyticsPayload,
    translations: dict[str, TranslatedArticle],
    keywords: list[str],
) -> tuple[float, str]:
    """
    Compute a heuristic confidence score (0.0-1.0).
    Returns (score, publish_status).

    Signals and weights:
    - Data Coverage:      0.20
    - Numeric Integrity:  0.25
    - Price Anomaly:      0.20
    - Output Validity:    0.15
    - Translation QA:     0.10
    - Keyword Coverage:   0.10
    """
    data_coverage   = _check_data_coverage(analytics)
    numeric_ok      = _check_numeric_in_article(article, analytics)
    price_ok        = _check_price_anomaly(analytics)
    validity        = _check_output_validity(article)
    keyword_cov     = _check_keyword_coverage(article, keywords)

    # Translation QA: average of numeric_integrity across translated languages
    if translations:
        trans_scores = [1.0 if t.numeric_integrity_passed else 0.0 for t in translations.values()]
        translation_qa = sum(trans_scores) / len(trans_scores)
    else:
        translation_qa = 1.0  # EN-only pass

    score = (
        0.20 * data_coverage
        + 0.25 * numeric_ok
        + 0.20 * price_ok
        + 0.15 * validity
        + 0.10 * translation_qa
        + 0.10 * keyword_cov
    )
    score = round(score, 3)

    if score >= CONFIDENCE_AUTO_PUBLISH:
        status = "published"
    elif score >= CONFIDENCE_REVIEW_REQUIRED:
        status = "review_required"
    else:
        status = "blocked"

    logger.info(
        "Confidence [%s]: %.3f → %s (cov=%.2f num=%.2f price=%.2f valid=%.2f trans=%.2f kw=%.2f)",
        analytics.scope_key, score, status,
        data_coverage, numeric_ok, price_ok, validity, translation_qa, keyword_cov,
    )
    return score, status


# ---------------------------------------------------------------------------
# JSON-LD rendering
# ---------------------------------------------------------------------------

def _plain_text(html: str) -> str:
    """Strip HTML tags to get plain article body text."""
    return re.sub(r"<[^>]+>", " ", html).strip()


def build_market_summary_table(analytics: AnalyticsPayload) -> list[MarketRow]:
    """Build a deterministic market summary table from analytics."""
    rows = analytics.markets or analytics.top_markets_by_price
    limit = 5 if analytics.article_type != "market_spotlight" else 1
    return [
        MarketRow(
            market=row.market,
            state=row.state,
            min_price=row.min_price,
            max_price=row.max_price,
            modal_price=row.modal_price,
            arrival_tonnes=row.arrival_tonnes,
        )
        for row in rows[:limit]
    ]


def build_meta_description(
    title: str,
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
) -> str:
    """Create a deterministic SEO description within search-friendly length."""
    parts = [
        f"{scope.scope_label} {analytics.commodity.title()} mandi bhav for {analytics.date}.",
        f"Avg modal price Rs {analytics.national_avg_modal:,.0f}.",
        f"Arrivals {analytics.national_total_arrivals:,.0f} tonnes.",
    ]
    if analytics.national_day_change_pct is not None:
        direction = "up" if analytics.national_day_change_pct >= 0 else "down"
        parts.append(
            f"Day change {abs(analytics.national_day_change_pct):.1f}% {direction}."
        )
    text = " ".join(parts)
    if len(text) > 165:
        text = text[:162].rstrip(" ,.-") + "..."
    if len(text) < 50:
        text = f"{title}. {text}"
    return text


def build_template_faqs(
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
) -> list[FAQItem]:
    """Build template FAQs directly from analytics."""
    faqs: list[FAQItem] = []
    commodity_name = analytics.commodity.title()

    faqs.append(
        FAQItem(
            question=f"What is the {commodity_name} mandi bhav in {scope.scope_label} today?",
            answer=(
                f"On {analytics.date}, the average modal price for {commodity_name.lower()} "
                f"in {scope.scope_label} is Rs {analytics.national_avg_modal:,.0f} per quintal."
            ),
        )
    )

    if analytics.top_markets_by_price:
        top_market = analytics.top_markets_by_price[0]
        faqs.append(
            FAQItem(
                question=f"Which market is quoting the strongest {commodity_name.lower()} price today?",
                answer=(
                    f"{top_market.market}, {top_market.state} is among the strongest reported markets "
                    f"today at Rs {top_market.modal_price:,.0f} per quintal."
                ),
            )
        )

    if analytics.national_total_arrivals:
        faqs.append(
            FAQItem(
                question=f"How much {commodity_name.lower()} arrival is reported today?",
                answer=(
                    f"Reported arrivals for this scope add up to about "
                    f"{analytics.national_total_arrivals:,.0f} tonnes on {analytics.date}."
                ),
            )
        )

    if len(faqs) < 3 and analytics.top_gainers:
        gainer = analytics.top_gainers[0]
        faqs.append(
            FAQItem(
                question=f"Which market showed the sharpest one-day move in {commodity_name.lower()}?",
                answer=(
                    f"{gainer.market}, {gainer.state} moved to Rs {gainer.modal_price:,.0f} per quintal, "
                    f"a change of {gainer.day_change_pct:.2f}% from the previous day."
                ),
            )
        )

    return faqs[:3]


def assemble_article_output(
    draft: ArticleDraft,
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
) -> ArticleOutput:
    """Expand a Gemini draft into the full deterministic English article payload."""
    from llm_engine import build_keywords

    return ArticleOutput(
        title=draft.title,
        meta_description=build_meta_description(draft.title, analytics, scope),
        body_html=draft.body_html,
        keywords=build_keywords(analytics.commodity, scope.article_type, scope),
        market_summary_table=build_market_summary_table(analytics),
        faqs=build_template_faqs(analytics, scope),
    )


def render_article_jsonld(
    article: ArticleOutput,
    date: str,
    language: str,
    commodity: str,
    article_type: str,
    scope_label: str,
) -> dict:
    """Render the NewsArticle JSON-LD schema via Jinja2 template."""
    env = _get_jinja_env()
    template = env.get_template("jsonld_article.j2")

    # Dateline: use scope_label for location context
    dateline = scope_label if scope_label not in ("National", "Best Market Advisory", "Top Gainers & Losers") else "India"

    rendered = template.render(
        title=article.title,
        meta_description=article.meta_description,
        date_iso=f"{date}T06:00:00+05:30",
        language_code=LANGUAGE_ISO.get(language, "en-IN"),
        keywords_csv=", ".join(article.keywords),
        dateline=dateline,
        article_body_plain=_plain_text(article.body_html),
    )
    return json.loads(rendered)


def render_faq_jsonld(article: ArticleOutput) -> dict:
    """Render the FAQPage JSON-LD schema via Jinja2 template."""
    env = _get_jinja_env()
    template = env.get_template("jsonld_faq.j2")
    rendered = template.render(faqs=article.faqs)
    return json.loads(rendered)


# ---------------------------------------------------------------------------
# Final article assembly and output
# ---------------------------------------------------------------------------

def assemble_final_article(
    article: ArticleOutput,
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
    language: str,
    confidence_score: float,
    publish_status: str,
    pipeline_run_id: str,
    translated: Optional[TranslatedArticle] = None,
) -> FinalArticleJSON:
    """
    Assemble the final FinalArticleJSON output for one article+language combination.
    If `translated` is provided, uses translated title/meta/body. Otherwise uses EN.
    """
    if translated:
        title = translated.title
        meta = translated.meta_description
        body = translated.body_html
    else:
        title = article.title
        meta = article.meta_description
        body = article.body_html

    # Rebuild article object for JSON-LD with correct title/meta
    rendering_article = ArticleOutput(
        title=title,
        meta_description=meta,
        body_html=body,
        keywords=article.keywords,
        market_summary_table=article.market_summary_table,
        faqs=article.faqs,
    )

    json_ld = render_article_jsonld(
        rendering_article,
        analytics.date,
        language,
        analytics.commodity,
        analytics.article_type,
        analytics.scope_label,
    )
    faq_json_ld = render_faq_jsonld(article)  # FAQs in EN regardless of article language

    return FinalArticleJSON(
        title=title,
        meta_description=meta,
        body=body,
        keywords=article.keywords,
        language=language,
        date=analytics.date,
        commodity=analytics.commodity,
        article_type=analytics.article_type,
        scope_key=analytics.scope_key,
        json_ld=json_ld,
        faq_json_ld=faq_json_ld,
        faqs=[{"question": f.question, "answer": f.answer} for f in article.faqs],
        confidence_score=confidence_score,
        publish_status=publish_status,
        pipeline_run_id=pipeline_run_id,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


def write_article_file(
    final_article: FinalArticleJSON,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """
    Write a FinalArticleJSON to disk.
    Path: output/{date}/{scope_key}/{language}.json
    Blocked articles go to output/{date}/blocked/{scope_key}_{language}.json
    Review articles go to output/{date}/review/{scope_key}_{language}.json
    """
    date = final_article.date
    lang = final_article.language
    scope = final_article.scope_key
    status = final_article.publish_status

    if status == "published":
        file_dir = output_dir / date / scope
        file_path = file_dir / f"{lang}.json"
    elif status == "review_required":
        file_dir = output_dir / date / "review"
        file_path = file_dir / f"{scope}_{lang}.json"
    else:  # blocked
        file_dir = output_dir / date / "blocked"
        file_path = file_dir / f"{scope}_{lang}.json"

    file_dir.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(final_article.model_dump(), f, ensure_ascii=False, indent=2)

    logger.debug("Written: %s", file_path)
    return file_path
