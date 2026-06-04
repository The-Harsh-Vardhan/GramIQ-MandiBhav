"""
llm_engine.py — Gemini API client and batched English article generation.

Gemini is used only for the creative parts of article writing:
1. English title
2. English body HTML

SEO metadata, keywords, FAQs, and tables are assembled deterministically in Python.
"""

import json
import logging
import re
import time
from typing import Optional

from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL, LLM_MAX_RETRIES, LLM_RETRY_DELAY_SECONDS, SEO_KEYWORDS
from schemas import AnalyticsPayload, ArticleDraft, ArticleOutput, ScopeTarget
from seo_assembler import assemble_article_output

logger = logging.getLogger("mandibhav.llm_engine")

_client: Optional[genai.Client] = None

GENERATION_SYSTEM_PROMPT = (
    "Write factual Indian mandi market articles from structured analytics only. "
    "Do not invent numbers, markets, or claims. Return JSON only."
)


def init_gemini() -> None:
    """Configure the Gemini API client. Call once at startup."""
    global _client
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file or set the environment variable."
        )
    _client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini API configured with model: %s", GEMINI_MODEL)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        init_gemini()
    return _client


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


def _compact_market(market: dict) -> dict:
    data = {
        "market": market.get("market"),
        "state": market.get("state"),
        "modal_price": round(float(market.get("modal_price", 0)), 2),
        "arrival_tonnes": round(float(market.get("arrival_tonnes", 0)), 2),
    }
    if market.get("day_change_pct") is not None:
        data["day_change_pct"] = round(float(market["day_change_pct"]), 2)
    if market.get("min_price") is not None:
        data["min_price"] = round(float(market["min_price"]), 2)
    if market.get("max_price") is not None:
        data["max_price"] = round(float(market["max_price"]), 2)
    return data


def _compact_payload(payload: AnalyticsPayload) -> dict:
    """Reduce prompt size by sending only structured facts needed for writing."""
    top_markets = [_compact_market(m.model_dump()) for m in payload.top_markets_by_price[:5]]
    bottom_markets = [_compact_market(m.model_dump()) for m in payload.bottom_markets_by_price[:3]]
    gainers = [_compact_market(m.model_dump()) for m in payload.top_gainers[:3]]
    losers = [_compact_market(m.model_dump()) for m in payload.top_losers[:3]]
    markets = [_compact_market(m.model_dump()) for m in payload.markets[:5]]

    compact = {
        "scope_key": payload.scope_key,
        "article_type": payload.article_type,
        "scope_label": payload.scope_label,
        "state": payload.state,
        "market": payload.market,
        "national_avg_modal": round(payload.national_avg_modal, 2),
        "national_total_arrivals": round(payload.national_total_arrivals, 2),
        "market_count": payload.market_count,
        "top_markets_by_price": top_markets,
    }
    if payload.national_day_change_pct is not None:
        compact["national_day_change_pct"] = round(payload.national_day_change_pct, 2)
    if payload.national_arrivals_change_pct is not None:
        compact["national_arrivals_change_pct"] = round(payload.national_arrivals_change_pct, 2)
    if bottom_markets:
        compact["bottom_markets_by_price"] = bottom_markets
    if gainers:
        compact["top_gainers"] = gainers
    if losers:
        compact["top_losers"] = losers
    if markets and payload.article_type in {"state_market_report", "market_spotlight"}:
        compact["markets"] = markets
    if payload.msp_current_year is not None:
        compact["msp_current_year"] = payload.msp_current_year
    if payload.price_vs_msp_pct is not None and payload.price_vs_msp_direction:
        compact["price_vs_msp"] = {
            "direction": payload.price_vs_msp_direction,
            "pct": payload.price_vs_msp_pct,
        }
    if payload.season_phase:
        compact["season_phase"] = payload.season_phase
    if payload.season_note:
        compact["season_note"] = payload.season_note
    if payload.market_significance:
        compact["market_significance"] = payload.market_significance
    return compact


def _build_batch_prompt(
    commodity: str,
    date: str,
    scope_payloads: dict[str, AnalyticsPayload],
) -> str:
    """Build a concise commodity-level generation prompt."""
    instructions = {
        "commodity": commodity,
        "date": date,
        "task": (
            "Write one English article per scope. Use only the supplied analytics. "
            "Each article must be 220-450 words of clean HTML with <h2>, <h3>, <p>, "
            "<table>, <tr>, <th>, <td>, and <strong> where useful."
        ),
        "article_rules": [
            "Keep all numbers exact.",
            "No markdown.",
            "Mention MSP or seasonal context only when present in analytics.",
            "Do not add FAQs, SEO metadata, keywords, or JSON-LD.",
        ],
        "output_schema": {
            "articles": [
                {
                    "scope_key": "string",
                    "title": "string",
                    "body_html": "string",
                }
            ]
        },
        "scopes": [_compact_payload(payload) for payload in scope_payloads.values()],
    }
    return json.dumps(instructions, ensure_ascii=False)


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
                temperature=0.4,
                max_output_tokens=8192,
            ),
        )
        return response.text
    except Exception as e:
        err_str = str(e)
        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
            match = re.search(r"retry.*?(\d+)s", err_str, re.IGNORECASE)
            wait = int(match.group(1)) + 2 if match else 30
            logger.warning("Rate limit hit. Waiting %ds before retry ...", wait)
            time.sleep(wait)
        else:
            logger.error("Gemini API call failed: %s", e)
        return None


def _parse_batch_response(raw_text: str) -> dict[str, ArticleDraft]:
    """Parse a batched Gemini response into validated article drafts."""
    data = json.loads(raw_text)
    articles = data.get("articles", [])
    parsed: dict[str, ArticleDraft] = {}
    for item in articles:
        scope_key = item["scope_key"]
        parsed[scope_key] = ArticleDraft(
            title=item["title"],
            body_html=item["body_html"],
        )
    return parsed


def generate_articles_for_commodity(
    commodity: str,
    date: str,
    scope_payloads: dict[str, AnalyticsPayload],
    scope_targets: dict[str, ScopeTarget],
) -> dict[str, ArticleOutput]:
    """
    Generate all missing English articles for a commodity in one Gemini call.
    Returns a dict of {scope_key: ArticleOutput}.
    """
    if not scope_payloads:
        return {}

    user_message = _build_batch_prompt(commodity, date, scope_payloads)
    correction_suffix = ""

    for attempt in range(1, LLM_MAX_RETRIES + 2):
        raw = _call_gemini_api(GENERATION_SYSTEM_PROMPT, user_message + correction_suffix)
        if raw:
            try:
                drafts = _parse_batch_response(raw)
                missing = set(scope_payloads) - set(drafts)
                if missing:
                    raise ValueError(f"Missing scopes in batch response: {sorted(missing)}")
                generated: dict[str, ArticleOutput] = {}
                for scope_key, draft in drafts.items():
                    payload = scope_payloads[scope_key]
                    scope = scope_targets[scope_key]
                    generated[scope_key] = assemble_article_output(draft, payload, scope)
                logger.info(
                    "Generated %d %s articles in batch attempt %d",
                    len(generated), commodity, attempt
                )
                return generated
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Batch parse/validation failed for %s: %s", commodity, e)
                correction_suffix = (
                    "\nReturn valid JSON only. Include one article object for every input scope_key."
                )

        if attempt <= LLM_MAX_RETRIES:
            logger.warning(
                "Generation attempt %d failed for %s. Retrying after %.1fs ...",
                attempt, commodity, LLM_RETRY_DELAY_SECONDS
            )
            time.sleep(LLM_RETRY_DELAY_SECONDS)

    logger.error("All generation attempts failed for commodity: %s", commodity)
    return {}
