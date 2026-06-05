"""
tests/test_date_management.py — Unit tests for date standardization, configurable OGD timeouts, and DB caching.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import config
from date_utils import normalize_date, parse_date, is_valid_date
from ingestion import LiveProvider, ingest_commodity, MockProvider
from schemas import MarketRecord
import database


def test_date_normalization():
    """Verify normalize_date parses various formats and returns YYYY-MM-DD."""
    # Standard ISO format
    assert normalize_date("2026-06-05") == "2026-06-05"
    assert normalize_date("2026/06/05") == "2026-06-05"
    
    # Slash separators (prioritize DD/MM/YYYY)
    assert normalize_date("05/06/2026") == "2026-06-05"
    assert normalize_date("06/05/2026") == "2026-05-06"
    
    # Hyphen separators (prioritize MM-DD-YYYY)
    assert normalize_date("06-05-2026") == "2026-06-05"
    assert normalize_date("05-06-2026") == "2026-05-06"
    
    # Unambiguous component resolution
    assert normalize_date("13-05-2026") == "2026-05-13"
    assert normalize_date("05-13-2026") == "2026-05-13"
    assert normalize_date("13/05/2026") == "2026-05-13"
    assert normalize_date("05/13/2026") == "2026-05-13"
    
    # Check validation
    assert is_valid_date("2026-06-05") is True
    assert is_valid_date("invalid-date-str") is False
    
    with pytest.raises(ValueError):
        normalize_date("invalid-date-str")


@patch("ingestion.requests.get")
def test_ogd_timeouts_applied(mock_get):
    """Verify that OGD API queries use configured connection and read timeouts."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"records": []}
    mock_get.return_value = mock_response

    # Force a dummy config state
    config.OGD_CONNECT_TIMEOUT = 8
    config.OGD_READ_TIMEOUT = 12

    provider = LiveProvider(api_key="mock_key", endpoint="https://api.example.com", resource_id="a0a0a0a0-b0b0-c0c0-d0d0-e0e0e0e0e0e0")
    try:
        provider.fetch_market_data("2026-06-05", "soybean", limit=1)
    except Exception:
        pass

    # Ensure get was called with correct timeout parameter
    assert mock_get.called
    kwargs = mock_get.call_args[1]
    assert "timeout" in kwargs
    assert kwargs["timeout"] == (8, 12)


def test_db_cache_hit_bypass_ogd():
    """Verify ingest_commodity skips OGD fetch when DB contains records for target date."""
    target_date = "2026-06-09"
    commodity = "soybean"
    
    # Create mock database rows
    mock_db_records = [
        {
            "id": 1,
            "commodity_slug": "soybean",
            "market_date": "2026-06-09",
            "state": "Maharashtra",
            "district": "Nagpur",
            "market_name": "Nagpur APMC",
            "variety": "Yellow",
            "grade": "FAQ",
            "min_price": 5000.0,
            "max_price": 5500.0,
            "modal_price": 5300.0,
            "arrival_tonnes": 50.0,
            "source": "ogd_api",
            "ingested_at": "2026-06-09 10:00:00"
        }
    ]
    
    # Patch database.query_market_data to simulate a cache hit
    with patch("database.query_market_data", return_value=mock_db_records) as mock_query, \
         patch("ingestion.LiveProvider.fetch_market_data") as mock_fetch:
        
        provider = LiveProvider(api_key="mock_key", endpoint="https://api.example.com", resource_id="a0a0a0a0-b0b0-c0c0-d0d0-e0e0e0e0e0e0")
        config.ingestion_data_source = ""
        
        records = ingest_commodity(target_date, commodity, provider)
        
        # Verify database query was called with normalized arguments
        mock_query.assert_called_once_with(commodity, target_date)
        
        # Verify OGD fetch was skipped entirely
        mock_fetch.assert_not_called()
        
        # Verify cache source state set
        assert config.ingestion_data_source == "CACHE"
        assert len(records) == 1
        assert records[0].market == "Nagpur APMC"
        assert records[0].modal_price == 5300.0
        assert records[0].date == "2026-06-09"
