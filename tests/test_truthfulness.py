"""
tests/test_truthfulness.py — Unit tests for truthfulness validation, credibility scoring,
and transparency disclosure injection.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import config
from schemas import AnalyticsPayload, ScopeTarget, ArticleOutput, TranslatedArticle
from seo_assembler import (
    validate_article_truthfulness,
    compute_credibility,
    build_disclosures,
    compute_confidence,
)

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_analytics():
    return AnalyticsPayload(
        commodity="soybean",
        date="2026-06-05",
        article_type="nagpur_demo",
        scope_key="soybean_nagpur",
        scope_label="Nagpur APMC",
        national_avg_modal=6625.0,
        national_total_arrivals=100.0,
        record_count=12,
        data_source_status="LIVE",
    )

@pytest.fixture
def base_scope():
    return ScopeTarget(
        commodity="soybean",
        article_type="nagpur_demo",
        scope_key="soybean_nagpur",
        scope_label="Nagpur APMC",
        state="Maharashtra",
        market="Nagpur APMC",
    )

# ---------------------------------------------------------------------------
# Truthfulness & Contradiction Detection Tests
# ---------------------------------------------------------------------------

def test_truthfulness_perfect_article(base_analytics, base_scope):
    """An article with no contradictions or unsupported terms should score 1.0."""
    body_html = (
        "<h2>Executive Summary</h2>"
        "<p>The market witnessed stable trading today. Prices averaged at Rs 6,625 per quintal.</p>"
        "<h2>Market Snapshot</h2>"
        "<p>Today's trading session reported consistent activity with a modal price of Rs 6,625.</p>"
    )
    contradictions, unsupported, scope_viols, score = validate_article_truthfulness(
        body_html, base_analytics, base_scope
    )
    assert contradictions == 0
    assert unsupported == 0
    assert scope_viols == 0
    assert score == 1.0


def test_truthfulness_arrivals_zero_contradictions(base_analytics, base_scope):
    """If arrivals are 0, supply-centric terms should trigger contradictions and lower score."""
    base_analytics.national_total_arrivals = 0.0
    body_html = (
        "<h2>Executive Summary</h2>"
        "<p>The mandi witnessed heavy arrivals and a substantial influx of supply today. "
        " bag and weighing platforms were extremely busy.</p>"
    )
    contradictions, unsupported, scope_viols, score = validate_article_truthfulness(
        body_html, base_analytics, base_scope
    )
    # "heavy arrivals", "substantial influx", "busy market"/platforms (or bagging and weighing)
    assert contradictions >= 2
    # Score should drop significantly
    assert score <= 0.0


def test_truthfulness_low_record_count_contradictions(base_analytics, base_scope):
    """If records count is < 5, talking about future outlook or trends should trigger contradictions."""
    base_analytics.record_count = 3
    body_html = (
        "<h2>Executive Summary</h2>"
        "<p>The regional demand indicates future outlook is positive. "
        "We analyze market trends and momentum here.</p>"
    )
    contradictions, unsupported, scope_viols, score = validate_article_truthfulness(
        body_html, base_analytics, base_scope
    )
    # "future outlook", "market trends", "trend"
    assert contradictions >= 1
    assert score < 1.0


def test_truthfulness_unsupported_claims(base_analytics, base_scope):
    """Terms like crusher demand, oil mill, liquidity are unsupported by raw data and should be flagged."""
    body_html = (
        "<p>Processors are buying soybean due to strong crusher demand. "
        "Oil mills are operating at capacity, improving market liquidity.</p>"
    )
    contradictions, unsupported, scope_viols, score = validate_article_truthfulness(
        body_html, base_analytics, base_scope
    )
    # "crusher", "oil mill", "processor", "liquidity"
    assert unsupported >= 4
    assert score < 1.0


def test_truthfulness_scope_violations(base_analytics, base_scope):
    """Nagpur scope article shouldn't make Maharashtra-wide or national generalizations."""
    base_scope.scope_key = "soybean_nagpur"
    body_html = (
        "<p>This report covers soybean prices across Maharashtra and the national soybean market. "
        "The regional economy has responded well to these regional trade flows.</p>"
    )
    contradictions, unsupported, scope_viols, score = validate_article_truthfulness(
        body_html, base_analytics, base_scope
    )
    # "across maharashtra", "national soybean market", "regional trade flows"
    assert scope_viols >= 3
    assert score < 1.0

# ---------------------------------------------------------------------------
# Credibility Scoring Tests
# ---------------------------------------------------------------------------

def test_credibility_live_perfect():
    """Live source with high record count should receive high credibility score."""
    score = compute_credibility(
        data_source_status="LIVE",
        record_count=20,
        generation_successful=True,
        translation_successful=True,
        contradictions_count=0,
    )
    assert score >= 0.95
    assert score <= 1.0


def test_credibility_mock_capped():
    """Mock source should be capped at 0.70 credibility score."""
    score = compute_credibility(
        data_source_status="MOCK",
        record_count=20,
        generation_successful=True,
        translation_successful=True,
        contradictions_count=0,
    )
    assert score == 0.70


def test_credibility_cache_capped():
    """Cache source should be capped at 0.70 credibility score."""
    score = compute_credibility(
        data_source_status="CACHE",
        record_count=15,
        generation_successful=True,
        translation_successful=True,
        contradictions_count=0,
    )
    assert score <= 0.70


def test_credibility_penalties():
    """Failures in generation or translation should penalize credibility score."""
    score_normal = compute_credibility(
        data_source_status="LIVE",
        record_count=10,
        generation_successful=True,
        translation_successful=True,
        contradictions_count=0,
    )
    score_penalized = compute_credibility(
        data_source_status="LIVE",
        record_count=10,
        generation_successful=False,  # fallback used
        translation_successful=False, # translation fallback used
        contradictions_count=0,
    )
    assert score_penalized < score_normal


def test_credibility_zeroed_by_contradictions():
    """Any contradictions should result in a 0.0 credibility score."""
    score = compute_credibility(
        data_source_status="LIVE",
        record_count=15,
        generation_successful=True,
        translation_successful=True,
        contradictions_count=1,
    )
    assert score == 0.0

# ---------------------------------------------------------------------------
# Disclosure Injection Tests
# ---------------------------------------------------------------------------

def test_disclosure_injection_english():
    """Disclosures should be formatted and appended/prepended in English."""
    body = "<p>Original Article Content</p>"
    body_with_disc, fallback_disc, ds_disc = build_disclosures(
        body=body,
        language="en",
        data_source_status="LIVE",
        report_type="LIMITED_DATA_REPORT",
        record_count=3,
        market_name="Nagpur APMC",
        generation_provider="local_fallback",
    )
    
    assert "Data Source:" in body_with_disc
    assert "Live OGD Data" in body_with_disc
    assert "Limited Data Notice:" in body_with_disc
    assert "Generated via Local Fallback Engine" in body_with_disc
    assert "Nagpur APMC" in body_with_disc
    assert fallback_disc is True
    assert ds_disc is True


def test_disclosure_injection_hindi():
    """Disclosures should be formatted and translated in Hindi."""
    body = "<p>मूल लेख</p>"
    body_with_disc, fallback_disc, ds_disc = build_disclosures(
        body=body,
        language="hi",
        data_source_status="MOCK",
        report_type="FULL_REPORT",
        record_count=15,
        market_name="नागपुर",
        generation_provider="gemini",
    )
    
    assert "डेटा स्रोत:" in body_with_disc
    assert "मॉक डेमो डेटा" in body_with_disc
    assert "स्रोत:" in body_with_disc
    assert "भारत सरकार ओजीडी" in body_with_disc
    assert "नागपुर" in body_with_disc
    # FULL_REPORT shouldn't have limited data notice
    assert "limited-data-notice" not in body_with_disc
    assert ds_disc is True

# ---------------------------------------------------------------------------
def test_confidence_gate_auto_publish_success(base_analytics):
    """Perfect live article meets confidence threshold and has no contradictions -> published."""
    # Ensure configuration thresholds are standard
    config.CONFIDENCE_AUTO_PUBLISH = 0.75
    
    article = ArticleOutput(
        title="Soybean Mandi Bhav Today: Maharashtra Live Market Price & Analysis",
        meta_description="Latest Soybean Mandi Bhav in Maharashtra. Average price is Rs 6,625 with arrivals of 100 tonnes.",
        body_html=(
            "<p>Consistent prices observed today. Modal rate is Rs 6,625.</p>"
            "<p>This is a long body paragraph to satisfy the pydantic validation rules. We want to ensure that the content is descriptive enough and meets the length requirements set by the schema. Prices remained stable. Local produce market committees reported steady transaction volumes today.</p>"
            "<p>To ensure we have enough words, let's write more paragraphs. The agricultural mandi network has witnessed stable activity for Soybean today. Market transactions reflect stable supply dynamics with steady rates. In Nagpur, agricultural produce market committees report consistent numbers, which has supported the local price structure. The trade flows continue to remain resilient.</p>"
            "<p>Trade volumes in major market yards indicate that the crop quality arriving at the platforms is satisfactory. Traders are participating in open auctions, and transactions are being settled. The steady rate of arrivals coupled with standard quality parameters has prevented any sudden volatility, maintaining a balanced environment in the agricultural ecosystem.</p>"
            "<p>Prices remain stable across major zones. The price spreads are narrow today, indicating uniform price patterns across the reporting centers. Market participants reported normal operations during the session.</p>"
            "<p>Furthermore, local agricultural committees and market supervisors have confirmed that the transactions are handled smoothly. Price charts indicate consistent trading within standard margins, ensuring a reliable trading experience for all participants. The agricultural infrastructure supports efficient sorting and weighing operations, contributing to overall market reliability. Market observers note that daily transactions are recorded under government oversight, which keeps the trade actions fully aligned with the regulations.</p>"
            "<p>In addition, trade parameters and crop updates from other areas are also influencing local expectations. However, domestic consumption patterns remain robust. Farmers should monitor local price spreads and make informed decisions on their produce based on their individual storage capacities and financial requirements. This continuous tracking of market rates is essential for maintaining supply chain efficiency and transparency.</p>"
            "<div class=\"gramiq-cta\">gramiq</div>"
        ),
        keywords=["Soybean", "Maharashtra", "Mandi", "Price", "Bhav", "Market"],
        faqs=[
            {"question": "What is the Soybean mandi bhav today?", "answer": "The average price is Rs 6,625 per quintal today."},
            {"question": "Which market is quoting strongest price?", "answer": "Nagpur APMC is quoting Rs 6,625 per quintal."},
            {"question": "How can I track price trends?", "answer": "Download the gramiq app to track daily alerts."}
        ]
    )
    
    # Let's verify that compute_confidence returns 'published'
    cred_score, status = compute_confidence(article, base_analytics, {}, article.keywords)
    assert cred_score >= 0.75
    assert status == "published"
 
 
def test_confidence_gate_review_due_to_contradiction(base_analytics):
    """Article with contradiction must be flagged for review regardless of score."""
    config.CONFIDENCE_AUTO_PUBLISH = 0.75
    base_analytics.national_total_arrivals = 0.0
    
    # Introduce "heavy arrivals" contradiction when arrivals is 0
    article = ArticleOutput(
        title="Soybean Mandi Bhav Today: Maharashtra Live Market Price & Analysis",
        meta_description="Latest Soybean Mandi Bhav in Maharashtra. Average price is Rs 6,625 with arrivals of 0 tonnes.",
        body_html=(
            "<p>We saw heavy arrivals today. Modal rate is Rs 6,625.</p>"
            "<p>This is a long body paragraph to satisfy the pydantic validation rules. We want to ensure that the content is descriptive enough and meets the length requirements set by the schema. Prices remained stable. Local produce market committees reported steady transaction volumes today.</p>"
            "<p>To ensure we have enough words, let's write more paragraphs. The agricultural mandi network has witnessed stable activity for Soybean today. Market transactions reflect stable supply dynamics with steady rates. In Nagpur, agricultural produce market committees report consistent numbers, which has supported the local price structure. The trade flows continue to remain resilient.</p>"
            "<p>Trade volumes in major market yards indicate that the crop quality arriving at the platforms is satisfactory. Traders are participating in open auctions, and transactions are being settled. The steady rate of arrivals coupled with standard quality parameters has prevented any sudden volatility, maintaining a balanced environment in the agricultural ecosystem.</p>"
            "<p>Prices remain stable across major zones. The price spreads are narrow today, indicating uniform price patterns across the reporting centers. Market participants reported normal operations during the session.</p>"
            "<p>Furthermore, local agricultural committees and market supervisors have confirmed that the transactions are handled smoothly. Price charts indicate consistent trading within standard margins, ensuring a reliable trading experience for all participants. The agricultural infrastructure supports efficient sorting and weighing operations, contributing to overall market reliability. Market observers note that daily transactions are recorded under government oversight, which keeps the trade actions fully aligned with the regulations.</p>"
            "<p>In addition, trade parameters and crop updates from other areas are also influencing local expectations. However, domestic consumption patterns remain robust. Farmers should monitor local price spreads and make informed decisions on their produce based on their individual storage capacities and financial requirements. This continuous tracking of market rates is essential for maintaining supply chain efficiency and transparency.</p>"
            "<div class=\"gramiq-cta\">gramiq</div>"
        ),
        keywords=["Soybean", "Maharashtra", "Mandi", "Price", "Bhav", "Market"],
        faqs=[
            {"question": "What is the Soybean mandi bhav today?", "answer": "The average price is Rs 6,625 per quintal today."},
            {"question": "Which market is quoting strongest price?", "answer": "Nagpur APMC is quoting Rs 6,625 per quintal."},
            {"question": "How can I track price trends?", "answer": "Download the gramiq app to track daily alerts."}
        ]
    )
    
    cred_score, status = compute_confidence(article, base_analytics, {}, article.keywords)
    assert status == "review_required" or status == "blocked"
