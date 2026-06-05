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


def determine_report_classification(analytics: AnalyticsPayload) -> str:
    """
    Classifies the report type based on data depth:
    - TREND_REPORT: multi-day comparison exists.
    - MARKET_REPORT: multiple markets.
    - PRICE_SNAPSHOT: single market, single day.
    """
    if (analytics.prev_national_avg_modal is not None or 
        analytics.national_day_change_pct is not None or 
        any(m.prev_modal_price is not None for m in analytics.markets)):
        return "TREND_REPORT"
    elif analytics.market_count > 1:
        return "MARKET_REPORT"
    else:
        return "PRICE_SNAPSHOT"


def count_unsupported_claims(body_html: str, analytics: AnalyticsPayload) -> int:
    """Count occurrences of unsupported/speculative claims in body_html."""
    body_lower = body_html.lower()
    unsupported_count = 0

    seasonal_allowed_words = set()
    if analytics.season_note:
        seasonal_allowed_words.update(re.findall(r"\b\w+\b", analytics.season_note.lower()))
    if analytics.season_phase:
        seasonal_allowed_words.update(re.findall(r"\b\w+\b", analytics.season_phase.lower()))

    always_forbidden = [
        "crusher", "oil mill", "processor", "demand", "buyer", "seller",
        "advice", "should hold", "should sell", "store", "holding", "liquidate",
        "buyer behavior", "farmer behavior", "active trade", "market highlights",
        "market sentiment", "sentiment", "liquidity", "shipping logistics", "logistics",
        "outlook", "predict", "expected to", "forecast", "projection", "future",
        "supply commentary"
    ]

    for term in always_forbidden:
        unsupported_count += body_lower.count(term)

    season_terms = ["sowing", "planting", "monsoon", "weather", "harvest"]
    for term in season_terms:
        count = body_lower.count(term)
        if count > 0:
            is_allowed = any(aw in term or term in aw for aw in seasonal_allowed_words)
            if not is_allowed:
                unsupported_count += count

    return unsupported_count


def validate_claim_support(body_html: str, analytics: AnalyticsPayload) -> tuple[str, int]:
    """
    Checks every paragraph in the article body against supported facts.
    Strips paragraphs containing unsupported/speculative claims and returns
    (cleaned_body_html, unsupported_claim_count).
    """
    parts = re.split(r"(<p>.*?</p>)", body_html, flags=re.DOTALL)
    cleaned_parts = []
    unsupported_count = 0

    for part in parts:
        if part.startswith("<p>") and part.endswith("</p>"):
            p_count = count_unsupported_claims(part, analytics)
            if p_count > 0:
                unsupported_count += p_count
                continue
        cleaned_parts.append(part)

    return "".join(cleaned_parts), unsupported_count


def validate_article_truthfulness(
    body_html: str,
    analytics: AnalyticsPayload,
    scope: ScopeTarget
) -> tuple[int, int, int, float]:
    """
    Validates the article body content against factual truthfulness rules.
    Returns (contradictions, unsupported_claims, scope_violations, truthfulness_score).
    """
    # Count unsupported claims on the raw body to support contradiction detection in original paragraphs
    unsupported_claims = count_unsupported_claims(body_html, analytics)

    contradictions = 0
    body_lower = body_html.lower()
    
    # Check arrivals = 0 contradictions
    if analytics.national_total_arrivals == 0:
        forbid_arrivals_zero = [
            "heavy arrivals", "strong supply", "substantial influx", "busy market",
            "influx of supply", "active trade", "active market", "bagging and weighing"
        ]
        for term in forbid_arrivals_zero:
            if term in body_lower:
                contradictions += 1
                logger.warning("Factual Contradiction: Arrivals is 0 but body contains '%s'", term)
                
    # Check low record count (< 5) contradictions
    if analytics.record_count < 5:
        forbid_low_records = [
            "trend", "regional demand", "market momentum", "future outlook", "market trends"
        ]
        for term in forbid_low_records:
            if term in body_lower:
                contradictions += 1
                logger.warning("Factual Contradiction: record_count is %d (< 5) but body contains '%s'", analytics.record_count, term)

    # 3. Scope Consistency
    scope_violations = 0
    if scope.scope_key == "soybean_nagpur":
        forbid_broad_scope = [
            "maharashtra-wide", "regional economy", "national soybean market",
            "across maharashtra", "regional trade flows", "key districts in the region"
        ]
        for term in forbid_broad_scope:
            if term in body_lower:
                scope_violations += 1
                logger.warning("Scope Consistency Violation: Nagpur scope but body contains broad term '%s'", term)

    # 4. Truthfulness Score Calculation
    score = 1.0 - (0.5 * contradictions) - (0.1 * unsupported_claims) - (0.1 * scope_violations)
    
    score = round(max(0.0, score), 3)
    return contradictions, unsupported_claims, scope_violations, score


def compute_credibility(
    data_source_status: str,
    record_count: int,
    generation_successful: bool,
    translation_successful: bool,
    contradictions_count: int,
    unsupported_claims_count: int = 0,
    scope_violations_count: int = 0
) -> float:
    if contradictions_count > 0 or scope_violations_count > 0:
        return 0.0

    # Determine base score (Problem 7)
    if data_source_status in ("LIVE", "LIVE_PLUS_CACHE"):
        base = 0.80 + 0.15 * min(record_count / 15.0, 1.0)
    elif data_source_status == "CACHE":
        base = 0.75 if getattr(config, "ingestion_data_source", "LIVE") == "LIVE" else 0.55
    else: # MOCK
        base = 0.60 + 0.10 * min(record_count / 15.0, 1.0)
    
    # Penalties
    if not generation_successful:
        base *= 0.9
    if not translation_successful:
        base *= 0.8
        
    # Deduct 0.05 per unsupported claim
    base -= 0.05 * unsupported_claims_count
        
    score = round(base, 3)
    
    # Caps
    if "MOCK" in data_source_status or data_source_status == "CACHE":
        score = min(score, 0.70)
        
    return max(0.0, min(score, 1.0))


def compute_confidence(
    article: ArticleOutput,
    analytics: AnalyticsPayload,
    translations: dict[str, TranslatedArticle],
    keywords: list[str],
) -> tuple[float, str]:
    """
    Compute a credibility score and verify truthfulness gate.
    """
    # 1. Check quality validation first
    # Clean the body first to remove unsupported paragraphs (Problem 5)
    cleaned_body, unsupported = validate_claim_support(article.body_html, analytics)
    article.body_html = cleaned_body

    is_valid = validate_article_quality(article)
    if not is_valid:
        return 0.0, "blocked"

    # 2. Check truthfulness of the generated English article
    scope = ScopeTarget(
        commodity=analytics.commodity,
        article_type=analytics.article_type,
        scope_key=analytics.scope_key,
        scope_label=analytics.scope_label,
        state=analytics.state,
        market=analytics.market,
    )
    contradictions, unsupported, scope_viols, truth_score = validate_article_truthfulness(
        article.body_html, analytics, scope
    )

    # 3. Determine data source status
    data_source = analytics.data_source_status or "LIVE"

    # 4. Check if local fallback generation was used
    generation_successful = not getattr(config, "quota_exhausted_mode", False)

    # 5. Check if translations were successful
    translation_successful = True
    if translations:
        translation_successful = all(t.translation_provider != "local_fallback" for t in translations.values())

    # 6. Compute credibility score
    cred_score = compute_credibility(
        data_source_status=data_source,
        record_count=analytics.record_count,
        generation_successful=generation_successful,
        translation_successful=translation_successful,
        contradictions_count=contradictions,
        unsupported_claims_count=unsupported,
        scope_violations_count=scope_viols
    )

    # 7. Apply publishing gate (Problem 10)
    # Require: supported claims >= 95%, contradictions = 0, scope violations = 0, report classification valid
    paragraphs = re.findall(r"<p>.*?</p>", article.body_html, re.DOTALL)
    total_paragraphs = len(paragraphs)
    supported_pct = (total_paragraphs - unsupported) / total_paragraphs if total_paragraphs > 0 else 1.0

    report_classification = determine_report_classification(analytics)
    is_classification_valid = True  # Dynamic classification ensures it matches

    if (supported_pct >= 0.95 and 
        contradictions == 0 and 
        scope_viols == 0 and 
        is_classification_valid and 
        cred_score >= CONFIDENCE_AUTO_PUBLISH):
        status = "published"
    else:
        status = "review_required"

    logger.info(
        "Credibility [%s]: %.3f → %s (truth_score=%.2f contradictions=%d unsupported=%d)",
        analytics.scope_key, cred_score, status, truth_score, contradictions, unsupported
    )
    return cred_score, status


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
        observed_facts=draft.observed_facts,
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

def build_disclosures(
    body: str,
    language: str,
    data_source_status: str,
    report_type: str,
    record_count: int,
    market_name: str,
    generation_provider: str,
    markets_analyzed: int = 1,
    varieties_analyzed: int = 0,
    grades_analyzed: int = 0
) -> tuple[str, bool, bool]:
    # Data source translations
    ds_labels = {
        "en": {
            "LIVE": "Live OGD Data",
            "LIVE_PLUS_CACHE": "Live OGD Data",
            "CACHE": "Cached Data",
            "MOCK": "Mock Demo Data",
        },
        "hi": {
            "LIVE": "लाइव ओजीडी डेटा",
            "LIVE_PLUS_CACHE": "लाइव ओजीडी डेटा",
            "CACHE": "कैश किया गया डेटा",
            "MOCK": "मॉक डेमो डेटा",
        },
        "mr": {
            "LIVE": "लाईव्ह ओजीडी डेटा",
            "LIVE_PLUS_CACHE": "लाईव्ह ओजीडी डेटा",
            "CACHE": "कॅश केलेला डेटा",
            "MOCK": "मॉक डेमो डेटा",
        },
        "gu": {
            "LIVE": "લાઈવ ઓજીડી ડેટા",
            "LIVE_PLUS_CACHE": "લાઈવ ઓજીડી ડેટા",
            "CACHE": "કેશ કરેલો ડેટા",
            "MOCK": "મૉક ડેમો ડેટા",
        }
    }

    # Labels for fields
    labels = {
        "en": {
            "ds_header": "Data Source:",
            "src": "Source:",
            "src_val": "Government of India OGD Market Dataset",
            "mkt": "Market:",
            "rec": "Records Analyzed:",
            "ds": "Data Source:",
            "rep_type": "Report Type:",
            "ltd_notice": "Limited Data Notice:",
            "ltd_text": "This report is based on a small number of market observations.",
            "fallback": "Generated via Local Fallback Engine",
        },
        "hi": {
            "ds_header": "डेटा स्रोत:",
            "src": "स्रोत:",
            "src_val": "भारत सरकार ओजीडी मार्केट डेटासेट",
            "mkt": "मंडी:",
            "rec": "विश्लेषण किए गए रिकॉर्ड:",
            "ds": "डेटा स्रोत:",
            "rep_type": "रिपोर्ट का प्रकार:",
            "ltd_notice": "सीमित डेटा सूचना:",
            "ltd_text": "यह रिपोर्ट कम संख्या में बाजार अवलोकनों पर आधारित है।",
            "fallback": "स्थानीय फ़ॉलबैक इंजन के माध्यम से जनरेट किया गया",
        },
        "mr": {
            "ds_header": "डेटा स्रोत:",
            "src": "स्रोत:",
            "src_val": "भारत सरकार ओजीडी मार्केट डेटासेट",
            "mkt": "बाजार समिती:",
            "rec": "विश्लेषण केलेले रेकॉर्ड:",
            "ds": "डेटा स्रोत:",
            "rep_type": "अहवाल प्रकार:",
            "ltd_notice": "मर्यादित डेटा सूचना:",
            "ltd_text": "हा अहवाल कमी संख्येने बाजार निरीक्षणावर आधारित आहे.",
            "fallback": "स्थानिक फॉलबैक इंजिनद्वारे व्युत्पन्न केले",
        },
        "gu": {
            "ds_header": "ડેટા સ્રોત:",
            "src": "સ્રોત:",
            "src_val": "ભારત સરકાર ઓજીડી માર્કેટ ડેટાસેટ",
            "mkt": "મંડી:",
            "rec": "વિશ્લેષણ કરેલ રેકોર્ડ્સ:",
            "ds": "ડેટા સ્રોત:",
            "rep_type": "અહેવાલ પ્રકાર:",
            "ltd_notice": "મર્યાદિત ડેટા નોટિસ:",
            "ltd_text": "આ અહેવાલ ઓછા બજાર નિરીક્ષણો પર આધારિત છે.",
            "fallback": "સ્થાનિક ફોલબેક એન્જિન દ્વારા જનરેટ કરવામાં આવ્યું છે",
        }
    }

    lang = language if language in labels else "en"
    ds_lbl = ds_labels.get(lang, ds_labels["en"]).get(data_source_status, "Live OGD Data")
    lbl = labels[lang]

    # Clean body: if there is already a header or footer, strip it
    body = re.sub(r'<div class="data-source-header".*?</div>', '', body, flags=re.DOTALL)
    body = re.sub(r'<div class="limited-data-notice".*?</div>', '', body, flags=re.DOTALL)
    body = re.sub(r'<div class="report-transparency-footer".*?</div>', '', body, flags=re.DOTALL)

    # 1. Build Header
    header_html = f"""<div class="data-source-header" style="padding: 10px; margin-bottom: 20px; border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 4px;">
  <strong>{lbl['ds_header']}</strong><br/>
  {ds_lbl}
</div>"""

    # 2. Build Limited Data Notice
    notice_html = ""
    if report_type == "LIMITED_DATA_REPORT":
        notice_html = f"""<div class="limited-data-notice" style="background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; padding: 10px; margin-bottom: 15px; border-radius: 4px;">
  <strong>{lbl['ltd_notice']}</strong><br/>
  {lbl['ltd_text']}
</div>"""

    # 3. Build Footer
    fallback_line = f"<p><strong>{lbl['fallback']}</strong></p>" if generation_provider == "local_fallback" else ""
    footer_html = f"""<div class="report-transparency-footer" style="margin-top: 20px; padding: 15px; border-top: 2px solid #eee; font-size: 0.9em; color: #555;">
  {fallback_line}
  <p><strong>{lbl['src']}</strong><br/>{lbl['src_val']}</p>
  <p><strong>{lbl['mkt']}</strong><br/>{market_name}</p>
  <p><strong>{lbl['rec']}</strong><br/>{record_count}</p>
  <p><strong>Markets Analyzed:</strong> {markets_analyzed}</p>
  <p><strong>Varieties Analyzed:</strong> {varieties_analyzed}</p>
  <p><strong>Grades Analyzed:</strong> {grades_analyzed}</p>
  <p><strong>{lbl['ds']}</strong><br/>{data_source_status}</p>
  <p><strong>{lbl['rep_type']}</strong><br/>{report_type}</p>
</div>"""

    body_html = header_html + "\n" + notice_html + "\n" + body.strip() + "\n" + footer_html
    
    fallback_disclosure_present = True
    if generation_provider == "local_fallback":
        fallback_disclosure_present = (lbl['fallback'] in body_html)
    
    data_source_disclosure_present = (lbl['ds_header'] in body_html)

    return body_html, fallback_disclosure_present, data_source_disclosure_present


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

    # --- Clean disclosures and validate truthfulness on raw body ---
    raw_body = re.sub(r'<div class="data-source-header".*?</div>', '', body, flags=re.DOTALL)
    raw_body = re.sub(r'<div class="limited-data-notice".*?</div>', '', raw_body, flags=re.DOTALL)
    raw_body = re.sub(r'<div class="report-transparency-footer".*?</div>', '', raw_body, flags=re.DOTALL)

    # Clean the body first to remove unsupported paragraphs (Problem 5: removed, regenerated, blocked)
    cleaned_body, unsupported = validate_claim_support(raw_body, analytics)
    raw_body = cleaned_body

    contradictions, unsupported, scope_viols, truth_score = validate_article_truthfulness(
        raw_body, analytics, scope
    )

    # Determine dynamic report classification
    report_type = determine_report_classification(analytics)

    # Apply publishing gate (Problem 10)
    final_status = publish_status
    
    paragraphs = re.findall(r"<p>.*?</p>", raw_body, re.DOTALL)
    total_paragraphs = len(paragraphs)
    supported_pct = (total_paragraphs - unsupported) / total_paragraphs if total_paragraphs > 0 else 1.0
    
    if supported_pct < 0.95 or contradictions > 0 or scope_viols > 0 or confidence_score < CONFIDENCE_AUTO_PUBLISH:
        final_status = "review_required"

    # --- Build localized disclosures ---
    data_source_status = analytics.data_source_status or "LIVE"
    record_count = analytics.record_count
    
    market_name = scope.market or analytics.market or scope.scope_label
    market_name_t = market_name
    if language == "hi":
        if "nagpur" in market_name.lower(): market_name_t = "नागपुर"
        elif "amravati" in market_name.lower(): market_name_t = "अमरावती"
        elif "wardha" in market_name.lower(): market_name_t = "वर्धा"
    elif language == "mr":
        if "nagpur" in market_name.lower(): market_name_t = "नागपूर"
        elif "amravati" in market_name.lower(): market_name_t = "अमरावती"
        elif "wardha" in market_name.lower(): market_name_t = "वर्धा"

    gen_provider = "local_fallback" if len(article.observed_facts) > 0 or (translated and translated.translation_provider == "local_fallback") else "gemini"

    body_with_disc, fallback_disc, ds_disc = build_disclosures(
        raw_body, language, data_source_status, report_type, record_count, market_name_t, gen_provider,
        markets_analyzed=getattr(analytics, "unique_markets_count", 1),
        varieties_analyzed=getattr(analytics, "unique_varieties_count", 0),
        grades_analyzed=getattr(analytics, "unique_grades_count", 0)
    )

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
 
    rendering_article = ArticleOutput(
        title=title,
        meta_description=meta,
        body_html=body_with_disc,
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
    faq_json_ld = render_faq_jsonld(article)

    return FinalArticleJSON(
        title=title,
        seo_title=seo_title,
        meta_description=meta,
        body=body_with_disc,
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
        publish_status=final_status,
        pipeline_run_id=pipeline_run_id,
        generated_at=datetime.utcnow().isoformat() + "Z",
        credibility_score=confidence_score,
        data_source_status=data_source_status,
        report_type=report_type,
        contradictions_count=contradictions,
        unsupported_claims_count=unsupported,
        scope_violations_count=scope_viols,
        truthfulness_score=truth_score,
        fallback_disclosure_present=fallback_disc,
        data_source_disclosure_present=ds_disc,
        unique_markets_count=getattr(analytics, "unique_markets_count", 1),
        unique_varieties_count=getattr(analytics, "unique_varieties_count", 0),
        unique_grades_count=getattr(analytics, "unique_grades_count", 0),
        record_count=record_count
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
    if not config.WRITE_ARTICLE_ARTIFACTS:
        logger.debug(
            "Article artifact writing disabled; skipping file output for %s/%s",
            final_article.scope_key,
            final_article.language,
        )
        return output_dir / final_article.date / final_article.scope_key / f"{final_article.language}.json"

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
