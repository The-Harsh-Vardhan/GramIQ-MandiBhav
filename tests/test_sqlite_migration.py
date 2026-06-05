import sqlite3

from migrate_sqlite_to_supabase import (
    slugify,
    sqlite_article_row_to_supabase,
    sqlite_market_row_to_supabase,
    sqlite_run_row_to_supabase,
)


def row_from_dict(payload: dict) -> sqlite3.Row:
    class FakeRow(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)

    return FakeRow(payload)  # type: ignore[return-value]


def test_slugify_normalizes_scope_strings():
    assert slugify("Soybean National 2026-06-06") == "soybean-national-2026-06-06"


def test_sqlite_article_row_to_supabase_maps_json_fields():
    row = row_from_dict(
        {
            "id": "legacy-1",
            "commodity_slug": "soybean",
            "article_date": "2026-06-06",
            "article_type": "daily_commodity_report",
            "scope_key": "soybean_national",
            "language": "en",
            "title": "Soybean mandi bhav today",
            "meta_description": "Structured summary of soybean mandi prices across India for the day.",
            "body_html": "<p>Body</p>",
            "keywords": '["Soybean", "Bhav"]',
            "json_ld": '{"@context":"https://schema.org","@type":"NewsArticle"}',
            "faq_json_ld": '{"@context":"https://schema.org","@type":"FAQPage"}',
            "faqs": '[{"question":"Q","answer":"A"}]',
            "pre_computed_analytics": '{"record_count":42,"data_source_status":"LIVE","report_type":"TREND_REPORT","scope_label":"National"}',
            "confidence_score": 0.88,
            "publish_status": "published",
            "pipeline_run_id": "run-1",
            "created_at": "2026-06-06T00:00:00Z",
        }
    )

    mapped = sqlite_article_row_to_supabase(row)

    assert mapped["slug"] == "soybean-soybean-national-2026-06-06"
    assert mapped["records_analyzed"] == 42
    assert mapped["report_type"] == "TREND_REPORT"
    assert mapped["keywords"] == ["Soybean", "Bhav"]


def test_sqlite_market_row_to_supabase_preserves_prices():
    row = row_from_dict(
        {
            "commodity_slug": "soybean",
            "market_date": "2026-06-06",
            "state": "Madhya Pradesh",
            "district": "Mandsaur",
            "market_name": "Mandsaur",
            "variety": "FAQ",
            "grade": "A",
            "min_price": 5000,
            "max_price": 5200,
            "modal_price": 5100,
            "arrival_tonnes": 12.5,
            "source": "ogd",
            "ingested_at": "2026-06-06T00:00:00Z",
        }
    )

    mapped = sqlite_market_row_to_supabase(row)

    assert mapped["market_name"] == "Mandsaur"
    assert mapped["modal_price"] == 5100
    assert mapped["arrival_tonnes"] == 12.5


def test_sqlite_run_row_to_supabase_maps_run_metrics():
    row = row_from_dict(
        {
            "run_id": "run-1",
            "run_date": "2026-06-06",
            "mode": "live",
            "articles_published": 8,
            "articles_review": 1,
            "articles_blocked": 0,
            "total_duration_seconds": 91.2,
            "status": "completed",
            "started_at": "2026-06-06T00:00:00Z",
            "completed_at": "2026-06-06T00:01:31Z",
        }
    )

    mapped = sqlite_run_row_to_supabase(row)

    assert mapped["id"] == "run-1"
    assert mapped["articles_generated"] == 8
    assert mapped["total_duration_seconds"] == 91.2
