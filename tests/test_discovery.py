import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import config
from mandibhav.discovery import (
    discover_metadata,
    generate_availability_report,
    find_available_markets,
    select_demo_market,
    find_latest_available_data,
    select_market_from_list,
)

@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """Ensure we are strictly in mock dev mode for unit testing."""
    monkeypatch.setattr(config, "PIPELINE_MODE", "dev")


def test_discover_metadata_mock():
    """Metadata discovery in mock mode should return valid categories."""
    meta = discover_metadata()
    assert "states" in meta
    assert "markets" in meta
    assert "commodities" in meta
    assert "varieties" in meta

    assert len(meta["states"]) > 0
    assert len(meta["markets"]) > 0
    assert "soybean" in [c.lower() for c in meta["commodities"]]


def test_generate_availability_report_mock():
    """Availability report should return formatted commodity counts."""
    report = generate_availability_report("2026-06-06")
    assert report["date"] == "2026-06-06"
    assert "commodities" in report
    
    commodities_lower = {k.lower(): v for k, v in report["commodities"].items()}
    # Mock data should contain Soybean or Cotton
    assert any(c in commodities_lower for c in ["soybean", "soyabean", "cotton"])


def test_find_available_markets_mock():
    """Finding available markets should return grouped lists sorted by records count."""
    markets = find_available_markets("soybean", "2026-06-06")
    assert len(markets) > 0
    
    # Check structure
    first = markets[0]
    assert "state" in first
    assert "district" in first
    assert "market" in first
    assert "records" in first
    
    # Verify sorted descending by records
    for i in range(len(markets) - 1):
        assert markets[i]["records"] >= markets[i+1]["records"]


def test_select_market_from_list():
    """Verify market selection priorities match specific requirements."""
    markets = [
        {"state": "Madhya Pradesh", "district": "Mandsaur", "market": "Mandsaur", "records": 12},
        {"state": "Maharashtra", "district": "Nagpur", "market": "Nagpur APMC", "records": 8},
        {"state": "Maharashtra", "district": "Amravati", "market": "Amravati", "records": 15},
    ]

    # Priority 1: User requested market exists
    selected = select_market_from_list(markets, preferred_market="Nagpur", preferred_state="Maharashtra")
    assert selected["market"] == "Nagpur APMC"

    # Priority 2: User requested market missing, but requested state exists (should pick highest in that state)
    selected = select_market_from_list(markets, preferred_market="Kukshi", preferred_state="Maharashtra")
    assert selected["market"] == "Amravati"  # Amravati has 15 records, Nagpur has 8

    # Priority 3: Commodity exists somewhere today (market with highest records overall)
    selected = select_market_from_list(markets, preferred_market="Kukshi", preferred_state="Gujarat")
    assert selected["market"] == "Amravati"  # Highest records overall


def test_select_demo_market_mock():
    """select_demo_market in mock mode should return matching date/market metadata."""
    res = select_demo_market(commodity_slug="soybean", target_date="2026-06-06")
    assert "date" in res
    assert "market" in res
    assert "state" in res
    assert "records" in res
    assert res["records"] > 0


def test_find_latest_available_data_mock():
    """find_latest_available_data should successfully resolve date/market details."""
    res = find_latest_available_data(
        commodity_slug="soybean",
        preferred_market="Nagpur",
        preferred_state="Maharashtra",
        target_date="2026-06-06"
    )
    assert "date" in res
    assert "market" in res
    assert "state" in res
    assert res["records"] > 0


def test_find_latest_available_data_supabase(monkeypatch):
    """Verify find_latest_available_data routes correctly when Supabase is enabled."""
    import supabase_backend
    monkeypatch.setattr(supabase_backend, "enabled", lambda: True)
    
    # Mock supabase_backend.query_latest_date_before_or_equal to return a dummy date
    monkeypatch.setattr(supabase_backend, "query_latest_date_before_or_equal", 
                        lambda comm, dt: "2026-06-05")
    
    # Mock supabase_backend.query_market_data to return some dummy records
    mock_records = [
        {"state": "Maharashtra", "district": "Nagpur", "market_name": "Nagpur APMC"},
        {"state": "Maharashtra", "district": "Nagpur", "market_name": "Nagpur APMC"},
        {"state": "Madhya Pradesh", "district": "Kukshi", "market_name": "Kukshi APMC"},
    ]
    monkeypatch.setattr(supabase_backend, "query_market_data", 
                        lambda comm, dt: mock_records)
    
    res = find_latest_available_data(
        commodity_slug="soybean",
        preferred_market="Nagpur",
        preferred_state="Maharashtra",
        target_date="2026-06-06"
    )
    
    assert res["date"] == "2026-06-05"
    assert res["market"] == "Nagpur APMC"
    assert res["state"] == "Maharashtra"
    assert res["records"] == 2

