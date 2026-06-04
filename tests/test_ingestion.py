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
from ingestion import MockProvider

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
