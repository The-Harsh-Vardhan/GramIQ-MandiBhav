import evaluate


def test_generate_report_uses_repository_when_artifacts_disabled(monkeypatch):
    sample_records = [
        {
            "id": "run-1:en:soybean_national:2026-06-06",
            "slug": "soybean-soybean-national-2026-06-06",
            "title": "Soybean mandi bhav today",
            "body_html": "<h2>Overview</h2><p>GramIQ report body with enough content.</p>",
            "meta_description": "Structured summary of soybean mandi prices across India for the day.",
            "keywords": ["Soybean", "Mandi", "Bhav"],
            "language": "en",
            "scope_key": "soybean_national",
            "article_type": "daily_commodity_report",
            "commodity_slug": "soybean",
            "credibility_score": 0.88,
            "publish_status": "published",
            "json_ld": {"@context": "https://schema.org", "@type": "NewsArticle"},
            "faq_json_ld": {"@context": "https://schema.org", "@type": "FAQPage"},
            "faqs": [{"question": "Q", "answer": "A"}],
            "unsupported_claims_count": 0,
            "contradictions_count": 0,
            "scope_violations_count": 0,
            "fallback_disclosure_present": True,
            "data_source_disclosure_present": True,
            "truthfulness_score": 1.0,
            "records_analyzed": 42,
            "unique_markets_count": 6,
            "unique_varieties_count": 2,
            "unique_grades_count": 1,
            "report_type": "TREND_REPORT",
            "data_source": "LIVE",
        }
    ]

    class FakeRepository:
        def list_articles_by_date(self, article_date, language=None):
            assert article_date == "2026-06-06"
            assert language is None
            return sample_records

    monkeypatch.setattr(evaluate.config, "DATA_BACKEND", "supabase")
    monkeypatch.setattr(evaluate.config, "WRITE_ARTICLE_ARTIFACTS", False)
    monkeypatch.setattr(evaluate, "ArticleRepository", FakeRepository)

    report = evaluate.generate_report("2026-06-06")

    assert report.total_files_scanned == 1
    assert report.articles_published == 1
    assert report.total_records_analyzed == 42
    assert report.pct_json_ld_valid == 100.0
