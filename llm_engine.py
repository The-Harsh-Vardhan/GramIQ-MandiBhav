"""
llm_engine.py — Gemini API client, prompt assembly, and output validation.

Uses the new google-genai SDK (google.genai).

Three-layer prompt architecture:
  Layer 1: System prompt (persona + absolute rules) — loaded from file
  Layer 2: Knowledge-enriched analytics context — built dynamically
  Layer 3: Article-type-specific generation instructions — from templates

Output is validated with Pydantic. Retries with error-correction on failure.
"""

import json
import logging
import re
import time
from typing import Optional

from google import genai
from google.genai import types
from pydantic import ValidationError

import config
from config import (
    GEMINI_API_KEY, GEMINI_MODEL, LLM_MAX_RETRIES, LLM_RETRY_DELAY_SECONDS,
    SEO_KEYWORDS, CTA_FOOTER_HTML, load_system_prompt, load_article_type_templates,
)
from schemas import (
    AnalyticsPayload, ArticleOutput, FAQItem, MarketRow, ScopeTarget
)

logger = logging.getLogger("mandibhav.llm_engine")

# Module-level client (initialized once)
_client: Optional[genai.Client] = None


# ---------------------------------------------------------------------------
# Gemini client initialization
# ---------------------------------------------------------------------------

def init_gemini() -> None:
    """Configure the Gemini API client. Call once at startup."""
    global _client
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file or set the environment variable."
        )
    _client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini API (google-genai) configured with model: %s", GEMINI_MODEL)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        init_gemini()
    return _client


# ---------------------------------------------------------------------------
# SEO keyword builder
# ---------------------------------------------------------------------------

def build_keywords(commodity: str, article_type: str, scope: ScopeTarget) -> list[str]:
    """Generate deterministic SEO keywords based on commodity, type, and scope."""
    keyword_templates = SEO_KEYWORDS.get(commodity, {})

    type_to_category = {
        "daily_commodity_report": "national",
        "state_market_report": "state",
        "market_spotlight": "market",
        "best_market_today": "best_market",
        "top_gainers_losers": "gainers_losers",
    }
    category = type_to_category.get(article_type, "national")
    templates = keyword_templates.get(category, keyword_templates.get("national", []))

    keywords = []
    for tmpl in templates:
        kw = tmpl
        if scope.state:
            kw = kw.replace("{state}", scope.state)
        if scope.market:
            kw = kw.replace("{market}", scope.market)
        keywords.append(kw)

    return keywords


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def build_analytics_context(payload: AnalyticsPayload) -> str:
    """Build the Layer 2 analytics context block injected into the prompt."""
    lines = [
        "=== PRE-COMPUTED MARKET ANALYTICS ===",
        f"Commodity: {payload.commodity.title()}",
        f"Date: {payload.date}",
        f"Scope: {payload.scope_label}",
        f"Total Reporting Markets: {payload.market_count}",
        "",
        "--- National Summary ---",
        f"National Average Modal Price: ₹{payload.national_avg_modal:,.0f}/quintal",
    ]

    if payload.national_day_change_pct is not None:
        direction = "▲ up" if payload.national_day_change_pct >= 0 else "▼ down"
        lines.append(
            f"Day-over-Day Change: {direction} {abs(payload.national_day_change_pct):.2f}%"
        )
    lines.append(f"Total Arrivals Today: {payload.national_total_arrivals:,.1f} tonnes")
    if payload.national_arrivals_change_pct is not None:
        arr_dir = "▲ up" if payload.national_arrivals_change_pct >= 0 else "▼ down"
        lines.append(
            f"Arrival Change: {arr_dir} {abs(payload.national_arrivals_change_pct):.1f}% vs yesterday"
        )

    if payload.state_summaries:
        lines.append("")
        lines.append("--- State-wise Aggregates ---")
        for ss in sorted(payload.state_summaries, key=lambda s: s.avg_modal_price, reverse=True):
            lines.append(
                f"  {ss.state}: avg ₹{ss.avg_modal_price:,.0f} | "
                f"arrivals {ss.total_arrivals:,.1f}T | {ss.market_count} markets"
            )

    if payload.top_markets_by_price:
        lines.append("")
        lines.append("--- Top Markets by Price ---")
        for m in payload.top_markets_by_price[:5]:
            delta_str = ""
            if m.day_change_pct is not None:
                sym = "▲" if m.day_change_pct >= 0 else "▼"
                delta_str = f" ({sym}{abs(m.day_change_pct):.1f}%)"
            lines.append(f"  {m.market} ({m.state}): ₹{m.modal_price:,.0f}{delta_str}")

    if payload.bottom_markets_by_price:
        lines.append("")
        lines.append("--- Bottom Markets by Price ---")
        for m in payload.bottom_markets_by_price[:3]:
            lines.append(f"  {m.market} ({m.state}): ₹{m.modal_price:,.0f}")

    if payload.top_gainers:
        lines.append("")
        lines.append("--- Top Gainers (Day-over-Day) ---")
        for m in payload.top_gainers:
            lines.append(
                f"  {m.market} ({m.state}): ₹{m.prev_modal_price:,.0f} → "
                f"₹{m.modal_price:,.0f} (+₹{m.day_change_abs:,.0f}, ▲{m.day_change_pct:.2f}%)"
            )
    if payload.top_losers:
        lines.append("")
        lines.append("--- Top Losers (Day-over-Day) ---")
        for m in payload.top_losers:
            lines.append(
                f"  {m.market} ({m.state}): ₹{m.prev_modal_price:,.0f} → "
                f"₹{m.modal_price:,.0f} (−₹{abs(m.day_change_abs):,.0f}, ▼{abs(m.day_change_pct):.2f}%)"
            )

    if payload.article_type in ("state_market_report", "market_spotlight") and payload.markets:
        lines.append("")
        lines.append("--- Individual Market Prices ---")
        for m in payload.markets:
            lines.append(
                f"  {m.market}: min ₹{m.min_price:,.0f} | "
                f"max ₹{m.max_price:,.0f} | modal ₹{m.modal_price:,.0f} | "
                f"arrivals {m.arrival_tonnes:.1f}T"
            )

    lines.append("")
    lines.append("=== DOMAIN KNOWLEDGE (interpret data with this context) ===")
    if payload.msp_current_year:
        lines.append(f"Government MSP (2025-26): ₹{payload.msp_current_year:,.0f}/quintal")
    if payload.price_vs_msp_pct and payload.price_vs_msp_direction:
        lines.append(
            f"Current Price vs MSP: {payload.price_vs_msp_direction.upper()} MSP by "
            f"{payload.price_vs_msp_pct:.2f}%"
        )
    if payload.season_phase:
        lines.append(f"Current Season Phase: {payload.season_phase}")
    if payload.season_note:
        lines.append(f"Seasonal Context: {payload.season_note}")
    if payload.commodity_description:
        lines.append(f"Commodity Context: {payload.commodity_description}")
    if payload.market_significance:
        lines.append(f"Market Significance: {payload.market_significance}")
    lines.append("IMPORTANT: Use the above ONLY to interpret data, never to invent numbers.")

    return "\n".join(lines)


def build_prompt(
    payload: AnalyticsPayload,
    scope: ScopeTarget,
    keywords: list[str],
    article_templates: dict,
    system_prompt: str,
) -> tuple[str, str]:
    """Build the full prompt. Returns (system_message, user_message)."""
    analytics_context = build_analytics_context(payload)

    template_config = article_templates.get(scope.article_type, {})
    template_str = template_config.get("template", "Write a market report.")
    word_target = template_config.get("word_target", "400-600")

    top_market = payload.top_markets_by_price[0] if payload.top_markets_by_price else None
    instructions = template_str.format(
        commodity=payload.commodity.title(),
        date=payload.date,
        state=scope.state or "India",
        market_name=scope.market or "",
        word_target=word_target,
        keywords=", ".join(f'"{k}"' for k in keywords),
        top_market=top_market.market if top_market else "",
        top_price=f"{top_market.modal_price:,.0f}" if top_market else "",
    )

    schema_instructions = """
=== OUTPUT FORMAT ===
You MUST respond with a valid JSON object matching this exact schema. No markdown, no explanatory text.

{
  "title": "string (max 120 chars, must include primary keyword and today's date)",
  "meta_description": "string (120-165 chars, engaging summary for search results)",
  "body_html": "string (full HTML article body with <h2>, <h3>, <p>, <table>, <strong> tags)",
  "keywords": ["array", "of", "2-8", "keyword", "strings"],
  "market_summary_table": [
    {"market": "string", "state": "string", "min_price": 0.0, "max_price": 0.0, "modal_price": 0.0, "arrival_tonnes": 0.0}
  ],
  "faqs": [
    {"question": "string (a question a farmer would search)", "answer": "string (factual answer from data)"},
    {"question": "string", "answer": "string"}
  ]
}

MANDATORY: body_html must end with this exact HTML footer (do not modify):
""" + CTA_FOOTER_HTML.strip()

    user_message = f"""
{analytics_context}

{instructions}

{schema_instructions}
"""
    return system_prompt, user_message


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------

def _call_gemini_api(system_prompt: str, user_message: str) -> Optional[str]:
    """Make a single Gemini API call and return the raw text response."""
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )
        return response.text
    except Exception as e:
        err_str = str(e)
        # Parse retryDelay from API error message if present (e.g. '27s')
        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
            match = re.search(r"retry.*?(\d+)s", err_str, re.IGNORECASE)
            wait = int(match.group(1)) + 2 if match else 30
            logger.warning(
                "Rate limit hit (429 RESOURCE_EXHAUSTED). Waiting %ds before retry ...", wait
            )
            time.sleep(wait)
        else:
            logger.error("Gemini API call failed: %s", e)
        return None


def _parse_and_validate(raw_text: str) -> Optional[ArticleOutput]:
    """Parse raw JSON text into ArticleOutput model."""
    try:
        data = json.loads(raw_text)
        return ArticleOutput(**data)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error: %s", e)
    except ValidationError as e:
        logger.warning("Pydantic validation error: %s", e)
    return None


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_article(
    payload: AnalyticsPayload,
    scope: ScopeTarget,
    knowledge: dict,
    system_prompt: str,
    article_templates: dict,
) -> Optional[ArticleOutput]:
    """
    Generate one English article for the given scope.
    Returns ArticleOutput or None if all retries fail.
    """
    keywords = build_keywords(payload.commodity, scope.article_type, scope)
    system_msg, user_msg = build_prompt(
        payload, scope, keywords, article_templates, system_prompt
    )

    logger.info("Generating: %s [%s]", scope.scope_key, scope.article_type)

    for attempt in range(1, LLM_MAX_RETRIES + 2):
        raw = _call_gemini_api(system_msg, user_msg)
        if raw:
            article = _parse_and_validate(raw)
            if article:
                logger.info(
                    "Generated %s (%d words, attempt %d)",
                    scope.scope_key, len(article.body_html.split()), attempt
                )
                return article
            else:
                user_msg += (
                    "\n\n[CORRECTION NEEDED] Your previous response was not valid JSON "
                    "matching the required schema. Please output ONLY the JSON object, "
                    "no markdown, no text outside the JSON braces."
                )

        if attempt <= LLM_MAX_RETRIES:
            logger.warning(
                "Attempt %d failed for %s. Retrying after %.1fs ...",
                attempt, scope.scope_key, LLM_RETRY_DELAY_SECONDS
            )
            time.sleep(LLM_RETRY_DELAY_SECONDS)

    logger.error("All attempts failed for: %s", scope.scope_key)
    return None
