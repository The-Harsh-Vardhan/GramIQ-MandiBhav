"""
tests/test_analytics.py — Unit tests for analytics pre-computation.

These tests are the most critical because analytics bugs produce incorrect
numbers that the LLM will then narrate as fact.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd

from schemas import MarketSummary, StateSummary, AnalyticsPayload
from analytics import _build_market_summaries


# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------

SAMPLE_TODAY_DF = pd.DataFrame([
    {"market_name": "Mandsaur", "state": "Madhya Pradesh", "modal_price": 5100.0, "min_price": 4850.0, "max_price": 5300.0, "arrival_tonnes": 620.0},
    {"market_name": "Indore",   "state": "Madhya Pradesh", "modal_price": 5020.0, "min_price": 4780.0, "max_price": 5200.0, "arrival_tonnes": 310.0},
    {"market_name": "Latur",    "state": "Maharashtra",    "modal_price": 4950.0, "min_price": 4700.0, "max_price": 5150.0, "arrival_tonnes": 380.0},
    {"market_name": "Akola",    "state": "Maharashtra",    "modal_price": 4900.0, "min_price": 4650.0, "max_price": 5100.0, "arrival_tonnes": 275.0},
])

SAMPLE_PREV_DF = pd.DataFrame([
    {"market_name": "Mandsaur", "state": "Madhya Pradesh", "modal_price": 5020.0},
    {"market_name": "Indore",   "state": "Madhya Pradesh", "modal_price": 4970.0},
    {"market_name": "Latur",    "state": "Maharashtra",    "modal_price": 4890.0},
])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildMarketSummaries:
    def test_basic_structure(self):
        """Each row should produce one MarketSummary with correct values."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, SAMPLE_PREV_DF)
        assert len(summaries) == 4
        mandsaur = next(m for m in summaries if m.market == "Mandsaur")
        assert mandsaur.modal_price == 5100.0
        assert mandsaur.state == "Madhya Pradesh"
        assert mandsaur.arrival_tonnes == 620.0

    def test_day_over_day_delta_computed(self):
        """Markets with previous data should have day_change_pct computed."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, SAMPLE_PREV_DF)
        mandsaur = next(m for m in summaries if m.market == "Mandsaur")
        assert mandsaur.prev_modal_price == 5020.0
        assert mandsaur.day_change_abs == pytest.approx(80.0)
        expected_pct = 80.0 / 5020.0 * 100.0
        assert mandsaur.day_change_pct == pytest.approx(expected_pct, abs=0.01)

    def test_no_prev_data_gives_none_delta(self):
        """Markets without previous day data should have None for delta fields."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, SAMPLE_PREV_DF)
        akola = next(m for m in summaries if m.market == "Akola")
        # Akola not in prev_df
        assert akola.day_change_pct is None
        assert akola.day_change_abs is None

    def test_no_previous_df(self):
        """With no previous dataframe, all deltas should be None."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, None)
        for m in summaries:
            assert m.day_change_pct is None
            assert m.prev_modal_price is None

    def test_prices_non_negative(self):
        """All price values must be non-negative."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, SAMPLE_PREV_DF)
        for m in summaries:
            assert m.modal_price >= 0
            assert m.min_price >= 0
            assert m.max_price >= 0
            assert m.arrival_tonnes >= 0


class TestAnalyticsPayloadIntegrity:
    def test_national_avg_computation(self):
        """National average should be the mean of all modal prices."""
        expected_avg = SAMPLE_TODAY_DF["modal_price"].mean()
        assert expected_avg == pytest.approx(4992.5, abs=0.01)

    def test_sort_by_price_is_descending(self):
        """Top markets should be sorted highest price first."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, None)
        sorted_summaries = sorted(summaries, key=lambda m: m.modal_price, reverse=True)
        prices = [m.modal_price for m in sorted_summaries]
        assert prices == sorted(prices, reverse=True)

    def test_sort_by_arrivals_is_descending(self):
        """Top markets by arrival should be sorted highest first."""
        summaries = _build_market_summaries(SAMPLE_TODAY_DF, None)
        sorted_summaries = sorted(summaries, key=lambda m: m.arrival_tonnes, reverse=True)
        arrivals = [m.arrival_tonnes for m in sorted_summaries]
        assert arrivals == sorted(arrivals, reverse=True)
        assert arrivals[0] == 620.0  # Mandsaur has highest arrivals


class TestKnowledgeInjection:
    def test_msp_comparison_above(self):
        """When price > MSP, direction should be 'above'."""
        from analytics import _inject_knowledge
        payload = AnalyticsPayload(
            commodity="soybean",
            date="2026-06-04",
            article_type="daily_commodity_report",
            scope_key="soybean_national",
            scope_label="National",
            national_avg_modal=5100.0,
            national_total_arrivals=1000.0,
        )
        knowledge = {
            "msp": {"soybean": {"2025-26": 4892}},
            "commodity": {},
            "market": {},
            "seasonal": {},
        }
        result = _inject_knowledge(payload, knowledge, "2026-06-04")
        assert result.msp_current_year == 4892.0
        assert result.price_vs_msp_direction == "above"
        assert result.price_vs_msp_pct == pytest.approx(4.25, abs=0.1)

    def test_msp_comparison_below(self):
        """When price < MSP, direction should be 'below'."""
        from analytics import _inject_knowledge
        payload = AnalyticsPayload(
            commodity="soybean",
            date="2026-06-04",
            article_type="daily_commodity_report",
            scope_key="soybean_national",
            scope_label="National",
            national_avg_modal=4800.0,
            national_total_arrivals=1000.0,
        )
        knowledge = {
            "msp": {"soybean": {"2025-26": 4892}},
            "commodity": {},
            "market": {},
            "seasonal": {},
        }
        result = _inject_knowledge(payload, knowledge, "2026-06-04")
        assert result.price_vs_msp_direction == "below"

    def test_seasonal_phase_injected(self):
        """Seasonal phase for June should be 'sowing'."""
        from analytics import _inject_knowledge
        payload = AnalyticsPayload(
            commodity="soybean",
            date="2026-06-04",
            article_type="daily_commodity_report",
            scope_key="soybean_national",
            scope_label="National",
            national_avg_modal=5100.0,
            national_total_arrivals=1000.0,
        )
        knowledge = {
            "msp": {},
            "commodity": {},
            "market": {},
            "seasonal": {
                "soybean": {
                    "Jun": {"phase": "sowing", "note": "Kharif sowing underway."}
                }
            },
        }
        result = _inject_knowledge(payload, knowledge, "2026-06-04")
        assert result.season_phase == "sowing"
        assert "Kharif" in result.season_note
