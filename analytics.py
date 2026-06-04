"""
analytics.py — Statistical pre-computation and scope matrix building.

This is the most critical module in the pipeline. It:
1. Queries raw market data from SQLite
2. Computes all statistical facts via pandas
3. Injects knowledge context (MSP, seasonality, market significance)
4. Builds the scope matrix — the list of articles to generate

The pre-computed analytics are passed to the LLM, which may ONLY use these
facts in its narrative. This is the anti-hallucination layer.
"""

import logging
from datetime import date as date_cls, datetime
from typing import Optional

import pandas as pd

import config
from config import (
    COMMODITIES, MIN_MARKETS_FOR_STATE_ARTICLE, TOP_MARKETS_FOR_SPOTLIGHT
)
from database import query_market_data, query_previous_day_data
from schemas import (
    MarketRecord, MarketSummary, StateSummary, AnalyticsPayload, ScopeTarget
)

logger = logging.getLogger("mandibhav.analytics")


# ---------------------------------------------------------------------------
# Helper: build MarketSummary with day-over-day delta
# ---------------------------------------------------------------------------

def _build_market_summaries(
    today_df: pd.DataFrame,
    prev_df: Optional[pd.DataFrame],
) -> list[MarketSummary]:
    """Construct MarketSummary objects with day-over-day deltas where available."""
    summaries: list[MarketSummary] = []

    # Build a lookup dict for previous day by (market, state)
    prev_lookup: dict[tuple, float] = {}
    if prev_df is not None and not prev_df.empty:
        for _, row in prev_df.iterrows():
            key = (str(row["market_name"]).strip(), str(row["state"]).strip())
            prev_lookup[key] = float(row["modal_price"])

    for _, row in today_df.iterrows():
        market = str(row["market_name"]).strip()
        state = str(row["state"]).strip()
        modal = float(row["modal_price"])
        prev_modal = prev_lookup.get((market, state))

        change_abs = (modal - prev_modal) if prev_modal else None
        change_pct = (change_abs / prev_modal * 100.0) if (prev_modal and prev_modal > 0) else None

        summaries.append(MarketSummary(
            market=market,
            state=state,
            modal_price=modal,
            min_price=float(row.get("min_price", 0)),
            max_price=float(row.get("max_price", 0)),
            arrival_tonnes=float(row.get("arrival_tonnes", 0)),
            prev_modal_price=prev_modal,
            day_change_abs=round(change_abs, 2) if change_abs is not None else None,
            day_change_pct=round(change_pct, 2) if change_pct is not None else None,
        ))

    return summaries


# ---------------------------------------------------------------------------
# Knowledge injection
# ---------------------------------------------------------------------------

def _inject_knowledge(
    payload: AnalyticsPayload,
    knowledge: dict,
    date: str,
) -> AnalyticsPayload:
    """Enrich an AnalyticsPayload with MSP, seasonal, and market context."""
    commodity = payload.commodity
    month_abbr = date_cls.fromisoformat(date).strftime("%b")  # e.g. "Jun"

    # MSP
    msp_data = knowledge.get("msp", {}).get(commodity, {})
    msp_value = msp_data.get("2025-26")
    if isinstance(msp_value, dict):
        # Cotton has staple-specific MSP — use medium staple as default
        msp_value = msp_value.get("medium_staple") or msp_value.get("long_staple")
    if msp_value:
        payload.msp_current_year = float(msp_value)
        diff = payload.national_avg_modal - float(msp_value)
        payload.price_vs_msp_pct = round(abs(diff) / float(msp_value) * 100.0, 2)
        payload.price_vs_msp_direction = "above" if diff >= 0 else "below"

    # Seasonal context
    seasonal_data = knowledge.get("seasonal", {}).get(commodity, {})
    month_data = seasonal_data.get(month_abbr, {})
    payload.season_phase = month_data.get("phase", "")
    payload.season_note = month_data.get("note", "")

    # Commodity description
    commodity_profile = knowledge.get("commodity", {}).get(commodity, {})
    payload.commodity_description = commodity_profile.get("description", "")

    # Market significance (for spotlight articles)
    if payload.market:
        market_profiles = knowledge.get("market", {})
        profile = market_profiles.get(payload.market, {})
        payload.market_significance = profile.get("significance", "")

    return payload


# ---------------------------------------------------------------------------
# Core analytics computation
# ---------------------------------------------------------------------------

def compute_analytics(
    commodity: str,
    date: str,
    knowledge: dict,
) -> dict[str, AnalyticsPayload]:
    """
    Compute analytics for a commodity on a given date.
    Returns a dict of {scope_key: AnalyticsPayload} for all scopes.
    """
    # Query data from SQLite
    today_rows = query_market_data(commodity, date)
    prev_rows = query_previous_day_data(commodity, date)

    if not today_rows:
        logger.warning("No market data for %s on %s", commodity, date)
        return {}

    today_df = pd.DataFrame(today_rows)
    prev_df = pd.DataFrame(prev_rows) if prev_rows else None

    # Build market summaries with deltas
    market_summaries = _build_market_summaries(today_df, prev_df)

    # National-level stats
    national_avg = today_df["modal_price"].mean()
    national_total_arrivals = today_df["arrival_tonnes"].sum()

    prev_national_avg = None
    prev_total_arrivals = None
    national_day_change_pct = None
    national_arrivals_change_pct = None
    if prev_df is not None and not prev_df.empty:
        prev_national_avg = prev_df["modal_price"].mean()
        prev_total_arrivals = prev_df["arrival_tonnes"].sum()
        if prev_national_avg and prev_national_avg > 0:
            national_day_change_pct = round(
                (national_avg - prev_national_avg) / prev_national_avg * 100.0, 2
            )
        if prev_total_arrivals and prev_total_arrivals > 0:
            national_arrivals_change_pct = round(
                (national_total_arrivals - prev_total_arrivals) / prev_total_arrivals * 100.0, 2
            )

    # State-level aggregations
    state_groups = today_df.groupby("state")
    state_summaries: list[StateSummary] = []
    for state_name, group in state_groups:
        top_row = group.loc[group["modal_price"].idxmax()]
        state_summaries.append(StateSummary(
            state=str(state_name),
            avg_modal_price=round(group["modal_price"].mean(), 2),
            total_arrivals=round(group["arrival_tonnes"].sum(), 2),
            market_count=len(group),
            top_market=str(top_row["market_name"]),
            top_market_price=float(top_row["modal_price"]),
        ))

    # Rankings
    sorted_by_price = sorted(market_summaries, key=lambda m: m.modal_price, reverse=True)
    top_5 = sorted_by_price[:5]
    bottom_5 = sorted_by_price[-5:]

    # Gainers and losers (only where we have prev-day data)
    markets_with_delta = [m for m in market_summaries if m.day_change_pct is not None]
    top_gainers = sorted(markets_with_delta, key=lambda m: m.day_change_pct or 0, reverse=True)[:3]
    top_losers = sorted(markets_with_delta, key=lambda m: m.day_change_pct or 0)[:3]

    results: dict[str, AnalyticsPayload] = {}

    # ---- 1. National scope ----
    national_key = f"{commodity}_national"
    national_payload = AnalyticsPayload(
        commodity=commodity,
        date=date,
        article_type="daily_commodity_report",
        scope_key=national_key,
        scope_label="National",
        national_avg_modal=round(national_avg, 2),
        prev_national_avg_modal=round(prev_national_avg, 2) if prev_national_avg else None,
        national_day_change_pct=national_day_change_pct,
        national_total_arrivals=round(national_total_arrivals, 2),
        prev_national_total_arrivals=round(prev_total_arrivals, 2) if prev_total_arrivals else None,
        national_arrivals_change_pct=national_arrivals_change_pct,
        state_summaries=state_summaries,
        markets=market_summaries,
        top_markets_by_price=top_5,
        bottom_markets_by_price=bottom_5,
        top_gainers=top_gainers,
        top_losers=top_losers,
        market_count=len(market_summaries),
    )
    national_payload = _inject_knowledge(national_payload, knowledge, date)
    results[national_key] = national_payload

    # ---- 2. State scopes ----
    states_with_enough_markets = [
        ss for ss in state_summaries if ss.market_count >= MIN_MARKETS_FOR_STATE_ARTICLE
    ]
    for ss in states_with_enough_markets:
        state_df = today_df[today_df["state"] == ss.state]
        prev_state_df = prev_df[prev_df["state"] == ss.state] if prev_df is not None else None
        state_markets = _build_market_summaries(state_df, prev_state_df)

        scope_key = f"{commodity}_{ss.state.lower().replace(' ', '_')}"
        payload = AnalyticsPayload(
            commodity=commodity,
            date=date,
            article_type="state_market_report",
            scope_key=scope_key,
            scope_label=ss.state,
            state=ss.state,
            national_avg_modal=round(national_avg, 2),
            national_day_change_pct=national_day_change_pct,
            national_total_arrivals=round(national_total_arrivals, 2),
            state_summaries=[ss],
            markets=state_markets,
            top_markets_by_price=sorted(state_markets, key=lambda m: m.modal_price, reverse=True)[:3],
            bottom_markets_by_price=sorted(state_markets, key=lambda m: m.modal_price)[:3],
            market_count=len(state_markets),
        )
        payload = _inject_knowledge(payload, knowledge, date)
        results[scope_key] = payload

    # ---- 3. Market spotlight scopes (top N by arrival volume) ----
    top_by_arrival = sorted(
        market_summaries, key=lambda m: m.arrival_tonnes, reverse=True
    )[:TOP_MARKETS_FOR_SPOTLIGHT]

    for ms in top_by_arrival:
        scope_key = f"{commodity}_{ms.market.lower().replace(' ', '_')}_spotlight"
        payload = AnalyticsPayload(
            commodity=commodity,
            date=date,
            article_type="market_spotlight",
            scope_key=scope_key,
            scope_label=ms.market,
            state=ms.state,
            market=ms.market,
            national_avg_modal=round(national_avg, 2),
            national_day_change_pct=national_day_change_pct,
            national_total_arrivals=round(national_total_arrivals, 2),
            state_summaries=[s for s in state_summaries if s.state == ms.state],
            markets=[ms],
            top_markets_by_price=[ms],
            market_count=1,
        )
        payload = _inject_knowledge(payload, knowledge, date)
        # Market significance from knowledge layer
        market_profiles = knowledge.get("market", {})
        profile = market_profiles.get(ms.market, {})
        payload.market_significance = profile.get("significance", "")
        results[scope_key] = payload

    # ---- 4. Best Market Today scope ----
    best_key = f"{commodity}_best_market_today"
    best_payload = AnalyticsPayload(
        commodity=commodity,
        date=date,
        article_type="best_market_today",
        scope_key=best_key,
        scope_label="Best Market Advisory",
        national_avg_modal=round(national_avg, 2),
        national_total_arrivals=round(national_total_arrivals, 2),
        markets=market_summaries,
        top_markets_by_price=sorted_by_price[:5],
        market_count=len(market_summaries),
    )
    best_payload = _inject_knowledge(best_payload, knowledge, date)
    results[best_key] = best_payload

    # ---- 5. Top Gainers & Losers scope ----
    gainers_key = f"{commodity}_gainers_losers"
    gainers_payload = AnalyticsPayload(
        commodity=commodity,
        date=date,
        article_type="top_gainers_losers",
        scope_key=gainers_key,
        scope_label="Top Gainers & Losers",
        national_avg_modal=round(national_avg, 2),
        national_day_change_pct=national_day_change_pct,
        national_total_arrivals=round(national_total_arrivals, 2),
        markets=market_summaries,
        top_gainers=top_gainers,
        top_losers=top_losers,
        market_count=len(market_summaries),
    )
    gainers_payload = _inject_knowledge(gainers_payload, knowledge, date)
    results[gainers_key] = gainers_payload

    logger.info(
        "Analytics computed for %s on %s: %d scopes generated",
        commodity, date, len(results)
    )
    return results


# ---------------------------------------------------------------------------
# Build scope targets for all commodities
# ---------------------------------------------------------------------------

def build_scope_matrix(date: str, knowledge: dict) -> tuple[dict[str, AnalyticsPayload], list[ScopeTarget]]:
    """
    Run analytics for all configured commodities.
    Returns (analytics_map, scope_targets_list).
    """
    all_analytics: dict[str, AnalyticsPayload] = {}
    scope_targets: list[ScopeTarget] = []

    for commodity in COMMODITIES:
        commodity_analytics = compute_analytics(commodity, date, knowledge)
        all_analytics.update(commodity_analytics)

        for scope_key, payload in commodity_analytics.items():
            scope_targets.append(ScopeTarget(
                commodity=payload.commodity,
                article_type=payload.article_type,
                scope_key=scope_key,
                scope_label=payload.scope_label,
                state=payload.state,
                market=payload.market,
            ))

    logger.info(
        "Scope matrix built: %d articles to generate for %s",
        len(scope_targets), date
    )
    return all_analytics, scope_targets
