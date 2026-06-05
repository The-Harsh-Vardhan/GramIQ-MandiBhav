"""
schemas.py — All Pydantic models used across the pipeline.

Defines: MarketRecord, AnalyticsPayload, ScopeTarget, FAQItem,
         MarketRow, ArticleOutput, TranslatedArticle, FinalArticleJSON.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Ingestion layer
# ---------------------------------------------------------------------------

class MarketRecord(BaseModel):
    """A single row of mandi price data — one market, one commodity, one date."""
    state: str
    district: str = ""
    market: str
    commodity: str
    variety: str = ""
    grade: str = ""
    min_price: float = Field(ge=0, default=0.0)
    max_price: float = Field(ge=0, default=0.0)
    modal_price: float = Field(ge=0)
    arrival_tonnes: float = Field(ge=0, default=0.0)
    date: str  # ISO format: YYYY-MM-DD

    @field_validator("state", "market", "commodity", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("modal_price", mode="after")
    @classmethod
    def modal_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("modal_price must be positive")
        return v


# ---------------------------------------------------------------------------
# Analytics layer
# ---------------------------------------------------------------------------

class MarketSummary(BaseModel):
    """Price summary for a single market (used in analytics payloads)."""
    market: str
    state: str
    modal_price: float
    min_price: float
    max_price: float
    arrival_tonnes: float
    prev_modal_price: Optional[float] = None
    day_change_abs: Optional[float] = None    # Today - Yesterday
    day_change_pct: Optional[float] = None    # % change


class StateSummary(BaseModel):
    """Aggregated summary for one state."""
    state: str
    avg_modal_price: float
    total_arrivals: float
    market_count: int
    top_market: str
    top_market_price: float


class AnalyticsPayload(BaseModel):
    """Pre-computed analytics for one (commodity, article_type, scope) combination."""
    commodity: str
    date: str
    article_type: str         # daily_commodity_report | state_market_report | etc.
    scope_key: str            # e.g. soybean_national | cotton_maharashtra
    scope_label: str          # Human-readable: "National" | "Maharashtra" | "Mandsaur"
    state: Optional[str] = None
    market: Optional[str] = None

    # National-level stats
    national_avg_modal: float
    prev_national_avg_modal: Optional[float] = None
    national_day_change_pct: Optional[float] = None
    national_total_arrivals: float
    prev_national_total_arrivals: Optional[float] = None
    national_arrivals_change_pct: Optional[float] = None

    # State-level aggregates
    state_summaries: list[StateSummary] = Field(default_factory=list)

    # Individual market details for this scope
    markets: list[MarketSummary] = Field(default_factory=list)

    # Derived rankings
    top_markets_by_price: list[MarketSummary] = Field(default_factory=list)
    bottom_markets_by_price: list[MarketSummary] = Field(default_factory=list)
    top_gainers: list[MarketSummary] = Field(default_factory=list)
    top_losers: list[MarketSummary] = Field(default_factory=list)

    # Scope metrics
    market_count: int = 0

    # Knowledge context (injected by analytics module)
    msp_current_year: Optional[float] = None
    price_vs_msp_pct: Optional[float] = None
    price_vs_msp_direction: Optional[str] = None   # "above" | "below"
    season_phase: Optional[str] = None
    season_note: Optional[str] = None
    commodity_description: Optional[str] = None
    market_significance: Optional[str] = None      # For spotlight articles
    record_count: int = 0
    data_source_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Article generation layer
# ---------------------------------------------------------------------------

class ScopeTarget(BaseModel):
    """Represents one article to be generated."""
    commodity: str
    article_type: str
    scope_key: str
    scope_label: str
    state: Optional[str] = None
    market: Optional[str] = None


class FAQItem(BaseModel):
    """A single FAQ question-answer pair."""
    question: str = Field(min_length=10)
    answer: str = Field(min_length=20)


class MarketRow(BaseModel):
    """A market price row for the summary table embedded in the article."""
    market: str
    state: str
    min_price: float
    max_price: float
    modal_price: float
    arrival_tonnes: float = 0.0


class ArticleOutput(BaseModel):
    """Structured output from Gemini for a single English article."""
    title: str = Field(min_length=10, max_length=120)
    meta_description: str = Field(min_length=50, max_length=165)
    body_html: str = Field(min_length=200)
    keywords: list[str] = Field(min_length=2, max_length=10)
    market_summary_table: list[MarketRow] = Field(default_factory=list)
    faqs: list[FAQItem] = Field(min_length=2, max_length=3)

    @field_validator("body_html", mode="after")
    @classmethod
    def body_must_contain_html(cls, v: str) -> str:
        if "<p>" not in v and "<h2>" not in v:
            raise ValueError("body_html must contain semantic HTML tags (<p> or <h2>)")
        return v


class ArticleDraft(BaseModel):
    """Minimal creative payload returned by Gemini before Python assembly."""
    title: str = Field(min_length=10, max_length=120)
    body_html: str = Field(min_length=200)
    observed_facts: list[str] = Field(default_factory=list)
    safe_inferences: list[str] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list)

    @field_validator("body_html", mode="after")
    @classmethod
    def body_must_contain_html(cls, v: str) -> str:
        if "<p>" not in v and "<h2>" not in v:
            raise ValueError("body_html must contain semantic HTML tags (<p> or <h2>)")
        return v


# ---------------------------------------------------------------------------
# Translation layer
# ---------------------------------------------------------------------------

class TranslatedArticle(BaseModel):
    """A translated version of one article in a target language."""
    language_code: str          # "hi" | "mr" | "gu"
    title: str
    meta_description: str
    body_html: str
    translation_provider: str   # "gemini"
    numeric_integrity_passed: bool = True
    length_ratio: float = 1.0


# ---------------------------------------------------------------------------
# Final output layer
# ---------------------------------------------------------------------------

class FinalArticleJSON(BaseModel):
    """
    The exact output format required by the GramIQ assignment spec.
    Written as a JSON file per article per language.
    """
    title: str
    seo_title: Optional[str] = None
    meta_description: str
    body: str                   # Full HTML article body
    keywords: list[str]
    language: str               # "en" | "hi" | "mr" | "gu"
    date: str                   # ISO: YYYY-MM-DD
    commodity: str
    article_type: str
    scope_key: str
    json_ld: dict               # NewsArticle schema.org payload
    faq_json_ld: dict           # FAQPage schema.org payload
    faqs: list[dict]            # [{"question": ..., "answer": ...}]
    confidence_score: float     # 0.0 – 1.0
    publish_status: str         # "published" | "review_required" | "blocked"
    pipeline_run_id: str
    generated_at: str           # ISO datetime
    credibility_score: float = 0.0
    data_source_status: str = "LIVE"
    report_type: str = "FULL_REPORT"
    contradictions_count: int = 0
    unsupported_claims_count: int = 0
    scope_violations_count: int = 0
    truthfulness_score: float = 1.0
    fallback_disclosure_present: bool = True
    data_source_disclosure_present: bool = True
