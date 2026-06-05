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

def validate_article_quality(article: ArticleOutput) -> bool:
    """
    Check if the article meets the minimum quality gates:
    - Word count >= 300
    - FAQ count >= 3
    - GramIQ CTA block present
    """
    # 1. Word count >= 300 (strip HTML tags)
    plain_text = re.sub(r"<[^>]+>", " ", article.body_html)
    word_count = len(plain_text.split())
    if word_count < 300:
        logger.warning("Article quality check failed: word count %d < 300", word_count)
        return False

    # 2. FAQ count >= 3
    if len(article.faqs) < 3:
        logger.warning("Article quality check failed: FAQ count %d < 3", len(article.faqs))
        return False

    # 3. GramIQ CTA block present
    cta_norm = re.sub(r"\s+", " ", config.CTA_FOOTER_HTML).strip().lower()
    body_norm = re.sub(r"\s+", " ", article.body_html).strip().lower()
    if cta_norm not in body_norm and "gramiq-cta" not in body_norm:
        logger.warning("Article quality check failed: GramIQ CTA block not found in body_html")
        return False

    return True


def generate_seo_metadata(
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
) -> tuple[str, str, list[str]]:
    """
    Generate deterministic SEO title, description, and keywords.
    - Title: 50-70 characters containing Commodity, Region, and intent keyword.
    - Description: 120-160 characters containing average modal price, arrivals, and region.
    - Keywords: list of keywords containing all 6 required terms.
    """
    commodity_name = analytics.commodity.title()
    region_name = scope.state or scope.market or scope.scope_label
    if region_name == "National":
        region_name = "India"

    # 1. SEO Title (50-70 characters)
    title = f"{commodity_name} Mandi Bhav Today: {region_name} Live Market Price & Analysis"
    if len(title) > 70:
        title = f"{commodity_name} Mandi Bhav Today: {region_name} Market Price"
    if len(title) > 70:
        title = f"{commodity_name} Mandi Bhav: {region_name} Price Updates"
    if len(title) > 70:
        title = f"{commodity_name} Mandi Bhav: {region_name} Rates"
    
    # Pad or slice to guarantee 50-70 characters
    if len(title) < 50:
        title = f"{title} | GramIQ MandiBhav Reports"
    if len(title) < 50:
        title = title.ljust(50, ".")
    elif len(title) > 70:
        title = title[:70]

    # 2. Meta Description (120-160 characters)
    avg_price = f"Rs {analytics.national_avg_modal:,.0f}"
    arrivals = f"{analytics.national_total_arrivals:,.0f} tonnes"
    desc = (
        f"Latest {commodity_name} Mandi Bhav in {region_name}. "
        f"Average modal price is {avg_price} with total arrivals of {arrivals}. "
        f"Get daily market reports and price analysis on GramIQ."
    )
    if len(desc) > 160:
        desc = (
            f"Latest {commodity_name} Mandi Bhav in {region_name}. "
            f"Average price is {avg_price} with arrivals of {arrivals}. "
            f"Read daily market report."
        )
    if len(desc) > 160:
        desc = f"Latest {commodity_name} Mandi Bhav in {region_name}: modal price is {avg_price}, arrivals are {arrivals}."

    # Pad or slice to guarantee 120-160 characters
    if len(desc) < 120:
        desc = desc + " Get real-time mandi alerts, price analysis, and farmer guidance updates on GramIQ."
    
    if len(desc) > 160:
        desc = desc[:157] + "..."
    elif len(desc) < 120:
        desc = desc.ljust(120, ".")

    # 3. Keywords (must contain the 6 terms: Commodity, Region, Mandi, Price, Bhav, Market)
    keywords = [
        commodity_name,
        region_name,
        "Mandi",
        "Price",
        "Bhav",
        "Market",
        f"{commodity_name} Mandi Bhav",
        f"{region_name} Mandi Bhav",
    ]
    seen = set()
    final_keywords = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            final_keywords.append(kw)
    
    return title, desc, final_keywords[:10]


def compute_confidence(
    article: ArticleOutput,
    analytics: AnalyticsPayload,
    translations: dict[str, TranslatedArticle],
    keywords: list[str],
) -> tuple[float, str]:
    """
    Compute a heuristic confidence score (0.0-1.0).
    Returns (score, publish_status).

    Formula: confidence = data_completeness_score * generation_success_score * translation_success_score
    """
    # 1. data_completeness_score: Fraction vs min_required
    if "national" in analytics.scope_key or analytics.article_type == "daily_commodity_report":
        min_required = 5
    elif "state" in analytics.scope_key or analytics.article_type == "state_market_report":
        min_required = 2
    else:
        min_required = 1

    reporting_markets = analytics.market_count
    fraction = reporting_markets / min_required
    data_completeness_score = min(fraction, 1.0)

    # Penalized by 0.8 if historical change (national_day_change_pct) is missing
    if analytics.national_day_change_pct is None:
        data_completeness_score *= 0.8

    # 2. generation_success_score: 1.0 if passes validation, else 0.0
    is_valid = validate_article_quality(article)
    generation_success_score = 1.0 if is_valid else 0.0

    # 3. translation_success_score: Average of numeric_integrity_passed (default 1.0 if EN-only)
    if translations:
        trans_scores = [1.0 if t.numeric_integrity_passed else 0.0 for t in translations.values()]
        translation_success_score = sum(trans_scores) / len(trans_scores)
    else:
        translation_success_score = 1.0

    score = data_completeness_score * generation_success_score * translation_success_score
    score = round(score, 3)

    # If quality checks fail, status is blocked and confidence is 0.0
    if not is_valid:
        score = 0.0
        status = "blocked"
    else:
        if score >= CONFIDENCE_AUTO_PUBLISH:
            status = "published"
        elif score >= CONFIDENCE_REVIEW_REQUIRED:
            status = "review_required"
        else:
            status = "blocked"

    logger.info(
        "Confidence [%s]: %.3f → %s (comp=%.2f gen=%.2f trans=%.2f)",
        analytics.scope_key, score, status,
        data_completeness_score, generation_success_score, translation_success_score,
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

    while len(faqs) < 3:
        faqs.append(
            FAQItem(
                question=f"How can I track daily {commodity_name.lower()} price trends?",
                answer=f"You can track daily {commodity_name.lower()} price trends, market arrivals, and processor demands on GramIQ."
            )
        )

    return faqs[:3]


def assemble_article_output(
    draft: ArticleDraft,
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
) -> ArticleOutput:
    """Expand a Gemini draft into the full deterministic English article payload."""
    title, meta_description, keywords = generate_seo_metadata(analytics, scope)
    
    body_html = draft.body_html
    if config.CTA_FOOTER_HTML not in body_html:
        body_html = body_html.strip() + "\n" + config.CTA_FOOTER_HTML

    return ArticleOutput(
        title=title,
        meta_description=meta_description,
        body_html=body_html,
        keywords=keywords,
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

    keywords = article.keywords
    if language != "en":
        lang_kws = {
            "hi": {
                "soybean": "सोयाबीन",
                "soyabean": "सोयाबीन",
                "cotton": "कपास",
                "maharashtra": "महाराष्ट्र",
                "gujarat": "गुजरात",
                "mandi": "मंडी",
                "price": "भाव",
                "bhav": "भाव",
                "market": "बाजार",
            },
            "mr": {
                "soybean": "सोयाबीन",
                "soyabean": "सोयाबीन",
                "cotton": "कापूस",
                "maharashtra": "महाराष्ट्र",
                "gujarat": "गुजरात",
                "mandi": "मंडी",
                "price": "भाव",
                "bhav": "भाव",
                "market": "बाजार",
            },
            "gu": {
                "soybean": "સોયાબીન",
                "soyabean": "સોયાબીન",
                "cotton": "કપાસ",
                "maharashtra": "મહારાષ્ટ્ર",
                "gujarat": "ગુજરાત",
                "mandi": "મંડી",
                "price": "ભાવ",
                "bhav": "ભાવ",
                "market": "બજાર",
            }
        }
        mapping = lang_kws.get(language, {})
        translated_kws = []
        for kw in keywords:
            mapped_kw = kw
            for eng_w, local_w in mapping.items():
                mapped_kw = re.sub(r'\b' + re.escape(eng_w) + r'\b', local_w, mapped_kw, flags=re.IGNORECASE)
            translated_kws.append(mapped_kw)
        keywords = translated_kws

    seo_title = None
    if getattr(config, "DEMO_MODE", False) and scope.scope_key == "soybean_nagpur":
        commodity_name = analytics.commodity.title()
        region_name = scope.market or scope.scope_label
        if language == "hi":
            comm_t = "सोयाबीन"
            reg_t = "नागपुर" if "nagpur" in region_name.lower() else ("अमरावती" if "amravati" in region_name.lower() else ("वर्धा" if "wardha" in region_name.lower() else region_name))
            seo_title = f"{reg_t} मंडी में आज {comm_t} का भाव"
        elif language == "mr":
            comm_t = "सोयाबीन"
            reg_t = "नागपूर" if "nagpur" in region_name.lower() else ("अमरावती" if "amravati" in region_name.lower() else ("वर्धा" if "wardha" in region_name.lower() else region_name))
            seo_title = f"{reg_t} बाजार समितीत आज {comm_t}चे दर"
        else:
            seo_title = f"{commodity_name} Price Today in {region_name} Mandi"
    else:
        seo_title = title

    # Rebuild article object for JSON-LD with correct title/meta
    rendering_article = ArticleOutput(
        title=title,
        meta_description=meta,
        body_html=body,
        keywords=keywords,
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
        seo_title=seo_title,
        meta_description=meta,
        body=body,
        keywords=keywords,
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

    # Write a copy to the global json cache folder for Task 8
    try:
        if getattr(config, "DEMO_MODE", False):
            cache_dir = output_dir / "json" / "demo"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_name = f"soybean_nagpur_latest_{lang}.json"
        else:
            cache_dir = output_dir / "json" / "production"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_name = f"article_{scope}_{lang}.json"
            
        cache_path = cache_dir / cache_name
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(final_article.model_dump(), f, ensure_ascii=False, indent=2)
        logger.debug("Cached copy written: %s", cache_path)
    except Exception as e:
        logger.warning("Failed to write cached copy (non-fatal): %s", e)

    return file_path
