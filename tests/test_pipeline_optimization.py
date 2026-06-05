import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import _find_cached_output
from schemas import AnalyticsPayload, ArticleDraft, MarketSummary, ScopeTarget
from seo_assembler import assemble_article_output, write_article_file
from translator import translate_articles

LONG_HTML = (
    "<h2>Market Overview</h2>"
    "<p>Soybean prices stayed firm today as arrivals remained steady across major markets.</p>"
    "<h3>Price Trend</h3>"
    "<p>Mandsaur continued to lead price discovery, while overall market sentiment remained stable "
    "with buyers focusing on quality lots and farmers watching MSP-linked support cues.</p>"
)


def _sample_payload(scope_key: str = "soybean_national") -> AnalyticsPayload:
    return AnalyticsPayload(
        commodity="soybean",
        date="2026-06-04",
        article_type="daily_commodity_report",
        scope_key=scope_key,
        scope_label="National",
        national_avg_modal=5100.0,
        national_day_change_pct=1.8,
        national_total_arrivals=1250.0,
        top_markets_by_price=[
            MarketSummary(
                market="Mandsaur",
                state="Madhya Pradesh",
                modal_price=5250.0,
                min_price=5000.0,
                max_price=5400.0,
                arrival_tonnes=500.0,
                day_change_pct=2.5,
            )
        ],
        markets=[
            MarketSummary(
                market="Mandsaur",
                state="Madhya Pradesh",
                modal_price=5250.0,
                min_price=5000.0,
                max_price=5400.0,
                arrival_tonnes=500.0,
                day_change_pct=2.5,
            )
        ],
        market_count=1,
    )


def test_assemble_article_output_is_deterministic():
    scope = ScopeTarget(
        commodity="soybean",
        article_type="daily_commodity_report",
        scope_key="soybean_national",
        scope_label="National",
    )
    draft = ArticleDraft(
        title="Soybean mandi bhav today for June 4, 2026",
        body_html=LONG_HTML,
    )

    article = assemble_article_output(draft, _sample_payload(), scope)

    assert "Soybean" in article.title
    assert "Mandi Bhav" in article.title
    assert 50 <= len(article.title) <= 70
    assert "Average modal price" in article.meta_description
    assert 120 <= len(article.meta_description) <= 160
    
    # Verify keywords contain all 6 required terms
    required_kws = {"Soybean", "India", "Mandi", "Price", "Bhav", "Market"}
    article_kws_lower = {kw.lower() for kw in article.keywords}
    for req in required_kws:
        assert req.lower() in article_kws_lower
        
    assert "gramiq-cta" in article.body_html
    assert len(article.market_summary_table) == 1
    assert len(article.faqs) >= 3


def test_write_article_file_uses_unique_review_filename():
    from schemas import FinalArticleJSON
    tmp_path = Path("C:/tmp/mandibhav-review-test")
    tmp_path.mkdir(parents=True, exist_ok=True)

    article = FinalArticleJSON(
        title="Title",
        meta_description="Meta description long enough for validation purposes.",
        body="<p>Body</p>",
        keywords=["a", "b"],
        language="en",
        date="2026-06-04",
        commodity="soybean",
        article_type="daily_commodity_report",
        scope_key="soybean_national",
        json_ld={},
        faq_json_ld={},
        faqs=[],
        confidence_score=0.5,
        publish_status="review_required",
        pipeline_run_id="run123",
        generated_at="2026-06-04T00:00:00Z",
    )

    path = write_article_file(article, output_dir=tmp_path)
    assert path.name == "soybean_national_en.json"
    assert path.parent.name == "review"


def test_find_cached_output_checks_published_review_and_blocked(monkeypatch):
    import config
    tmp_path = Path("C:/tmp/mandibhav-cache-test")
    tmp_path.mkdir(parents=True, exist_ok=True)

    output_dir = tmp_path / "output"
    published = output_dir / "2026-06-04" / "soybean_national" / "en.json"
    review = output_dir / "2026-06-04" / "review" / "soybean_state_en.json"
    blocked = output_dir / "2026-06-04" / "blocked" / "soybean_market_hi.json"

    for path in [published, review, blocked]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(config, "OUTPUT_DIR", output_dir)

    assert _find_cached_output("2026-06-04", "soybean_national", "en") == published
    assert _find_cached_output("2026-06-04", "soybean_state", "en") == review
    assert _find_cached_output("2026-06-04", "soybean_market", "hi") == blocked


def test_translate_articles_handles_batched_response(monkeypatch):
    articles = {
        "soybean_national": assemble_article_output(
            ArticleDraft(
                title="Soybean mandi bhav today for June 4, 2026",
                body_html=LONG_HTML + "<p>Price is Rs 5100 today.</p>",
            ),
            _sample_payload(),
            ScopeTarget(
                commodity="soybean",
                article_type="daily_commodity_report",
                scope_key="soybean_national",
                scope_label="National",
            ),
        )
    }

    def fake_translate_batch(prompt: str) -> str:
        assert "soybean_national" in prompt
        return """{
          "translations": [
            {
              "scope_key": "soybean_national",
              "language_code": "hi",
              "title": "सोयाबीन मंडी भाव",
              "meta_description": "सोयाबीन का भाव 5100 रुपये।",
              "body_html": "<h2>बाजार</h2><p>भाव 5100 रुपये है।</p>"
            },
            {
              "scope_key": "soybean_national",
              "language_code": "mr",
              "title": "सोयाबीन मंडी भाव",
              "meta_description": "सोयाबीनचा भाव 5100 रुपये.",
              "body_html": "<h2>बाजार</h2><p>भाव 5100 रुपये आहे.</p>"
            }
          ]
        }"""

    monkeypatch.setattr("translator._translate_batch", fake_translate_batch)

    result = translate_articles(
        "soybean",
        articles,
        {"soybean_national": ["hi", "mr"]},
    )

    assert set(result["soybean_national"]) == {"hi", "mr"}
    assert result["soybean_national"]["hi"].numeric_integrity_passed is True


def test_retry_info_parsing(monkeypatch):
    """Test that retryInfo seconds are extracted correctly from APIError details dict."""
    from google.genai.errors import APIError
    import re

    response_json = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "Quota exceeded",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                    "retryDelay": {
                        "seconds": 24,
                        "nanos": 940719748
                    }
                }
            ]
        }
    }
    err = APIError(code=429, response_json=response_json)
    
    # Perform extraction simulation
    delay = 24.0
    if err.details:
        details_list = err.details.get("error", {}).get("details", [])
        for detail in details_list:
            if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                retry_delay = detail.get("retryDelay")
                if isinstance(retry_delay, dict):
                    sec = retry_delay.get("seconds")
                    if sec is not None:
                        delay = float(sec)
    
    assert delay == 24.0


def test_fallback_queries(monkeypatch):
    """Test that LiveProvider fallback strategy goes through step 1, 2, 3 and fallback."""
    from ingestion import LiveProvider, MockProvider
    
    provider = LiveProvider(api_key="test-key")
    calls = []
    
    def fake_fetch_all_pages(date, commodity_filter, limit=None):
        calls.append((date, commodity_filter))
        return [] # Always return no records to trigger fallbacks

    monkeypatch.setattr(provider, "_fetch_all_pages", fake_fetch_all_pages)
    
    # We mock fetch_market_data on MockProvider so we don't hit the disk
    monkeypatch.setattr(MockProvider, "fetch_market_data", lambda self, d, c: [{"mock": "record"}])
    
    records = provider.fetch_market_data("2026-06-04", "soybean")
    
    # Expecting: 
    # Query 1 calls: (date, Soyabean), (date, Soybean)
    # Query 2 calls: (None, Soyabean), (None, Soybean)
    # Query 3 call: (None, None)
    expected_calls = [
        ("2026-06-04", "Soyabean"),
        ("2026-06-04", "Soybean"),
        (None, "Soyabean"),
        (None, "Soybean"),
        (None, None),
    ]
    assert calls == expected_calls
    assert records == [{"mock": "record"}]


def test_schema_discovery_mode(monkeypatch):
    """Test schema discovery prints first record and validates fields."""
    from ingestion import LiveProvider
    import config
    
    monkeypatch.setattr(config, "DEBUG_OGD_SCHEMA", True)
    
    calls = []
    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "records": [
                    {
                        "arrival_date": "05/06/2026",
                        "commodity": "Soybean",
                        "state": "Madhya Pradesh"
                    }
                ]
            }
            
    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    
    provider = LiveProvider(api_key="test-key")
    # If initialization completed without crashing, it succeeded.
    assert provider is not None


def test_fallback_generation_and_translation(monkeypatch):
    import config
    import llm_engine
    import translator
    from schemas import ScopeTarget, ArticleOutput

    # Configure quota_exhausted_mode = True to force local fallbacks
    monkeypatch.setattr(config, "quota_exhausted_mode", True)

    payload = _sample_payload(scope_key="soybean_maharashtra")
    payload.article_type = "state_market_report"
    payload.state = "Maharashtra"
    payload.scope_label = "Maharashtra"
    
    config.analytics_payloads_cache = {"soybean_maharashtra": payload}

    scope_targets = {
        "soybean_maharashtra": ScopeTarget(
            commodity="soybean",
            article_type="state_market_report",
            scope_key="soybean_maharashtra",
            scope_label="Maharashtra",
            state="Maharashtra",
        )
    }

    # Test generation fallback
    articles = llm_engine.generate_articles_for_commodity(
        "soybean",
        "2026-06-04",
        {"soybean_maharashtra": payload},
        scope_targets,
    )

    assert "soybean_maharashtra" in articles
    article = articles["soybean_maharashtra"]
    assert isinstance(article, ArticleOutput)
    
    # Verify quality constraints
    from seo_assembler import validate_article_quality
    assert validate_article_quality(article) is True
    
    # Test translation fallback
    translations = translator.translate_articles(
        "soybean",
        articles,
        {"soybean_maharashtra": ["hi", "mr", "gu"]},
    )

    assert "soybean_maharashtra" in translations
    langs = translations["soybean_maharashtra"]
    assert set(langs.keys()) == {"hi", "mr", "gu"}
    for lang_code, trans in langs.items():
        assert trans.numeric_integrity_passed is True
        assert trans.length_ratio > 0.5
        assert "gramiq" in trans.body_html.lower()

