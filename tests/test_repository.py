import repository
from schemas import AnalyticsPayload, FinalArticleJSON, ScopeTarget


def build_sample_article() -> tuple[FinalArticleJSON, AnalyticsPayload, ScopeTarget]:
    analytics = AnalyticsPayload(
        commodity="soybean",
        date="2026-06-06",
        article_type="daily_commodity_report",
        scope_key="soybean_national",
        scope_label="National",
        national_avg_modal=5100,
        national_total_arrivals=1200,
        state_summaries=[],
        markets=[],
        top_markets_by_price=[],
        bottom_markets_by_price=[],
        top_gainers=[],
        top_losers=[],
        market_count=18,
        record_count=120,
        data_source_status="LIVE",
        unique_markets_count=18,
        unique_varieties_count=4,
        unique_grades_count=2,
    )
    scope = ScopeTarget(
        commodity="soybean",
        article_type="daily_commodity_report",
        scope_key="soybean_national",
        scope_label="National",
    )
    article = FinalArticleJSON(
        title="Soybean mandi bhav today",
        seo_title="Soybean mandi bhav today",
        meta_description="Structured summary of soybean mandi prices across India for the day.",
        body="<p>Daily report body.</p>",
        keywords=["Soybean", "Mandi", "Bhav"],
        language="en",
        date="2026-06-06",
        commodity="soybean",
        article_type="daily_commodity_report",
        scope_key="soybean_national",
        json_ld={},
        faq_json_ld={},
        faqs=[],
        confidence_score=0.88,
        publish_status="published",
        pipeline_run_id="run-123",
        generated_at="2026-06-06T00:00:00Z",
        credibility_score=0.88,
        data_source_status="LIVE",
        report_type="TREND_REPORT",
        contradictions_count=0,
        unsupported_claims_count=0,
        scope_violations_count=0,
        truthfulness_score=1.0,
        fallback_disclosure_present=True,
        data_source_disclosure_present=True,
        unique_markets_count=18,
        unique_varieties_count=4,
        unique_grades_count=2,
        record_count=120,
    )
    return article, analytics, scope


def test_build_article_slug_is_stable():
    article, _, _ = build_sample_article()
    assert repository.build_article_slug(article) == "soybean-soybean-national-2026-06-06"


def test_build_article_record_contains_transparency_fields():
    article, analytics, scope = build_sample_article()
    record = repository.build_article_record(article, analytics, scope)

    assert record["slug"] == "soybean-soybean-national-2026-06-06"
    assert record["records_analyzed"] == 120
    assert record["credibility_score"] == 0.88
    assert record["report_type"] == "TREND_REPORT"
    assert record["market_name"] == "National"
