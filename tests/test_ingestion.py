"""
tests/test_ingestion.py — Unit tests for data ingestion and validation.

Uses an in-project temp directory (tests/tmp/) to avoid Windows
permission errors with pytest's tmp_path on some systems.
"""

import sys
import csv
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from schemas import MarketRecord
from ingestion import LiveProvider, MockProvider

# In-project temp dir — avoids Windows AppData\Temp permission issues
TMP_DIR = Path(__file__).parent / "tmp"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_tmp():
    """Create and clean the local temp directory before/after each test."""
    TMP_DIR.mkdir(exist_ok=True)
    yield
    shutil.rmtree(TMP_DIR, ignore_errors=True)


VALID_ROW = {
    "state": "Madhya Pradesh",
    "district": "Mandsaur",
    "market": "Mandsaur",
    "commodity": "Soybean",
    "variety": "Yellow",
    "grade": "FAQ",
    "min_price": "4850",
    "max_price": "5300",
    "modal_price": "5100",
    "arrival_tonnes": "620",
    "date": "2026-06-01",
}


def write_csv(rows: list[dict], filename: str = "soybean_sample.csv") -> Path:
    """Write rows to a CSV inside TMP_DIR and return the path."""
    path = TMP_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# MockProvider tests
# ---------------------------------------------------------------------------

class TestMockProvider:
    def test_loads_valid_csv(self):
        """MockProvider should load and validate a well-formed CSV."""
        write_csv([VALID_ROW])
        provider = MockProvider(mock_dir=TMP_DIR)
        records = provider.fetch_market_data("2026-06-04", "soybean")
        assert len(records) == 1
        assert records[0].market == "Mandsaur"
        assert records[0].modal_price == 5100.0

    def test_date_is_overridden(self):
        """The date from the CSV should be overridden with the requested date."""
        write_csv([VALID_ROW])  # CSV has date 2026-06-01
        provider = MockProvider(mock_dir=TMP_DIR)
        records = provider.fetch_market_data("2026-06-04", "soybean")
        assert records[0].date == "2026-06-04"  # Must be overridden

    def test_invalid_row_skipped(self):
        """Rows with invalid modal_price (zero) should be skipped."""
        bad_row = {**VALID_ROW, "modal_price": "0"}
        write_csv([VALID_ROW, bad_row])  # One valid, one invalid
        provider = MockProvider(mock_dir=TMP_DIR)
        records = provider.fetch_market_data("2026-06-04", "soybean")
        assert len(records) == 1  # Only the valid row loaded

    def test_missing_csv_returns_empty(self):
        """If the CSV file doesn't exist, return empty list without crashing."""
        provider = MockProvider(mock_dir=TMP_DIR)  # tmp dir is empty
        records = provider.fetch_market_data("2026-06-04", "soybean")
        assert records == []

    def test_multiple_rows_loaded(self):
        """All valid rows should be loaded."""
        rows = [
            VALID_ROW,
            {**VALID_ROW, "market": "Indore", "modal_price": "5020"},
            {**VALID_ROW, "market": "Ujjain", "modal_price": "4880", "state": "Madhya Pradesh"},
        ]
        write_csv(rows)
        provider = MockProvider(mock_dir=TMP_DIR)
        records = provider.fetch_market_data("2026-06-04", "soybean")
        assert len(records) == 3
        markets = {r.market for r in records}
        assert markets == {"Mandsaur", "Indore", "Ujjain"}


# ---------------------------------------------------------------------------
# MarketRecord schema tests
# ---------------------------------------------------------------------------

class TestMarketRecordSchema:
    def test_valid_record(self):
        record = MarketRecord(
            state="Maharashtra",
            market="Latur",
            commodity="Soybean",
            modal_price=4950.0,
            date="2026-06-04",
        )
        assert record.modal_price == 4950.0
        assert record.min_price == 0.0  # default
        assert record.max_price == 0.0  # default

    def test_strips_whitespace(self):
        record = MarketRecord(
            state="  Madhya Pradesh  ",
            market=" Mandsaur ",
            commodity=" Soybean ",
            modal_price=5100.0,
            date="2026-06-04",
        )
        assert record.state == "Madhya Pradesh"
        assert record.market == "Mandsaur"
        assert record.commodity == "Soybean"

    def test_zero_modal_price_invalid(self):
        with pytest.raises(Exception):
            MarketRecord(
                state="Maharashtra",
                market="Latur",
                commodity="Soybean",
                modal_price=0.0,
                date="2026-06-04",
            )

    def test_negative_price_invalid(self):
        with pytest.raises(Exception):
            MarketRecord(
                state="Maharashtra",
                market="Latur",
                commodity="Soybean",
                modal_price=-100.0,
                date="2026-06-04",
            )

    def test_arrival_tonnes_defaults_to_zero(self):
        record = MarketRecord(
            state="Gujarat",
            market="Rajkot",
            commodity="Cotton",
            modal_price=7200.0,
            date="2026-06-04",
        )
        assert record.arrival_tonnes == 0.0

    def test_full_record(self):
        record = MarketRecord(
            state="Gujarat",
            district="Rajkot",
            market="Rajkot",
            commodity="Cotton",
            variety="Long Staple",
            grade="FAQ",
            min_price=6800.0,
            max_price=7500.0,
            modal_price=7200.0,
            arrival_tonnes=520.0,
            date="2026-06-04",
        )
        assert record.min_price == 6800.0
        assert record.max_price == 7500.0
        assert record.arrival_tonnes == 520.0


class TestLiveProvider:
    def test_parse_ogd_records_converts_quintals_to_tonnes(self):
        provider = LiveProvider(api_key="test-key")
        records = provider._parse_ogd_records(
            [
                {
                    "State_Name": "Madhya Pradesh",
                    "District_Name": "Mandsaur",
                    "Market_Name": "Mandsaur",
                    "Variety": "Soyabean",
                    "Grade": "FAQ",
                    "Min_Price": "4850",
                    "Max_Price": "5300",
                    "Modal_Price": "5100",
                    "Arrivals_in_Qtl": "6200",
                }
            ],
            date="2026-06-04",
            commodity="soybean",
        )

        assert len(records) == 1
        assert records[0].arrival_tonnes == 620.0
        assert records[0].modal_price == 5100.0

    def test_fetch_market_data_tries_alias_filters_until_data_found(self, monkeypatch):
        provider = LiveProvider(api_key="test-key")
        calls = []

        def fake_fetch_all_pages(date: str, commodity_filter: str) -> list[dict]:
            calls.append((date, commodity_filter))
            if commodity_filter == "Soyabean":
                return [{"Modal_Price": "5100", "State_Name": "MP", "Market_Name": "Mandsaur"}]
            return []

        def fake_parse(raw_records: list[dict], date: str, commodity: str) -> list[MarketRecord]:
            return [
                MarketRecord(
                    state="Madhya Pradesh",
                    market="Mandsaur",
                    commodity=commodity,
                    modal_price=5100.0,
                    date=date,
                )
            ]

        monkeypatch.setattr(provider, "_fetch_all_pages", fake_fetch_all_pages)
        monkeypatch.setattr(provider, "_parse_ogd_records", fake_parse)

        records = provider.fetch_market_data("2026-06-04", "soybean")

        assert len(records) == 1
        assert calls == [("2026-06-04", "Soyabean")]

    def test_validation_invalid_endpoint(self):
        """LiveProvider should fail to initialize with an invalid endpoint URL."""
        with pytest.raises(ValueError, match="endpoint must start with http"):
            LiveProvider(api_key="test-key", endpoint="invalid-url")

    def test_validation_invalid_resource_id(self):
        """LiveProvider should fail to initialize with an invalid Resource ID format."""
        with pytest.raises(ValueError, match="Resource ID must be a valid UUID format"):
            LiveProvider(api_key="test-key", resource_id="invalid-uuid")

    def test_connection_success(self, monkeypatch):
        """test_connection() should return success = True when API call is successful."""
        from ingestion import test_connection
        import requests

        class MockResponse:
            status_code = 200
            def json(self):
                return {"records": [{"some": "data"}]}

        def mock_get(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(requests, "get", mock_get)
        monkeypatch.setattr(LiveProvider, "validate_config", lambda self: None)

        res = test_connection()
        assert res["success"] is True
        assert res["status_code"] == 200
        assert res["records"] == 1
        assert res["error"] is None

    def test_connection_failure(self, monkeypatch):
        """test_connection() should handle errors gracefully and return success = False."""
        from ingestion import test_connection
        import requests

        def mock_get(*args, **kwargs):
            raise requests.Timeout("Timeout testing")

        monkeypatch.setattr(requests, "get", mock_get)
        monkeypatch.setattr(LiveProvider, "validate_config", lambda self: None)

        res = test_connection()
        assert res["success"] is False
        assert res["records"] == 0
        assert "Timeout" in res["error"]
