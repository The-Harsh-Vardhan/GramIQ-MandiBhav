"""
ingestion.py — DataProvider abstraction with MockProvider and LiveProvider.

Usage:
    from ingestion import get_provider
    provider = get_provider(config)
    records = provider.fetch_market_data("2026-06-04", "soybean")
"""

import csv
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config
from config import (
    PIPELINE_MODE, MOCK_DIR, OGD_API_KEY, OGD_API_BASE_URL, OGD_RESOURCE_IDS
)
from schemas import MarketRecord
from database import insert_market_records, query_market_data

logger = logging.getLogger("mandibhav.ingestion")


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------

class DataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def fetch_market_data(self, date: str, commodity: str) -> list[MarketRecord]:
        """
        Return a validated list of MarketRecord objects.
        date: ISO format string 'YYYY-MM-DD'
        commodity: 'soybean' or 'cotton'
        """
        ...

    @abstractmethod
    def fetch_previous_day_data(self, date: str, commodity: str) -> list[MarketRecord]:
        """Return market data for the day preceding `date`."""
        ...


# ---------------------------------------------------------------------------
# Mock provider (development mode)
# ---------------------------------------------------------------------------

class MockProvider(DataProvider):
    """
    Loads realistic market data from CSV fixtures.
    The date in CSV rows is overridden with the requested date so the
    pipeline works identically regardless of which date is requested.
    """

    def __init__(self, mock_dir: Path = MOCK_DIR):
        self.mock_dir = Path(mock_dir)

    def _load_csv(self, csv_path: Path, override_date: str) -> list[MarketRecord]:
        """Parse a CSV file and validate each row as a MarketRecord."""
        if not csv_path.exists():
            logger.warning("Mock CSV not found: %s", csv_path)
            return []

        records: list[MarketRecord] = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):  # Row 2 = first data row
                try:
                    record = MarketRecord(
                        state=row.get("state", "").strip(),
                        district=row.get("district", "").strip(),
                        market=row.get("market", "").strip(),
                        commodity=row.get("commodity", "").strip(),
                        variety=row.get("variety", "").strip(),
                        grade=row.get("grade", "").strip(),
                        min_price=float(row.get("min_price", 0) or 0),
                        max_price=float(row.get("max_price", 0) or 0),
                        modal_price=float(row.get("modal_price", 0) or 0),
                        arrival_tonnes=float(row.get("arrival_tonnes", 0) or 0),
                        date=override_date,  # Always override with requested date
                    )
                    records.append(record)
                except Exception as e:
                    logger.warning("Row %d in %s skipped: %s", i, csv_path.name, e)

        logger.info("MockProvider: loaded %d records from %s", len(records), csv_path.name)
        return records

    def fetch_market_data(self, date: str, commodity: str) -> list[MarketRecord]:
        csv_path = self.mock_dir / f"{commodity}_sample.csv"
        return self._load_csv(csv_path, override_date=date)

    def fetch_previous_day_data(self, date: str, commodity: str) -> list[MarketRecord]:
        # Compute the previous date from the requested date
        from datetime import date as date_cls, timedelta
        prev_date = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
        csv_path = self.mock_dir / f"{commodity}_previous_day.csv"
        return self._load_csv(csv_path, override_date=prev_date)


# ---------------------------------------------------------------------------
# Live provider (production mode)
# ---------------------------------------------------------------------------

class LiveProvider(DataProvider):
    """
    Fetches live market data from the data.gov.in OGD REST API.
    Requires OGD_API_KEY to be set in environment.
    """

    def __init__(self, api_key: str = OGD_API_KEY):
        self.api_key = api_key
        if not self.api_key:
            logger.warning("OGD_API_KEY not set. LiveProvider may fail.")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _call_ogd_api(self, resource_id: str, date: str, limit: int = 500) -> list[dict]:
        """Make a single API call to OGD and return raw records list."""
        # OGD date format: DD/MM/YYYY
        from datetime import date as date_cls
        d = date_cls.fromisoformat(date)
        ogd_date = d.strftime("%d/%m/%Y")

        params = {
            "api-key": self.api_key,
            "format": "json",
            "limit": limit,
            "filters[Arrival_Date]": ogd_date,
        }
        url = f"{OGD_API_BASE_URL}/{resource_id}"

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            records = data.get("records", [])
            logger.info("OGD API returned %d records for date=%s", len(records), date)
            return records
        except requests.HTTPError as e:
            logger.error("OGD API HTTP error: %s", e)
            raise

    def _parse_ogd_records(self, raw_records: list[dict], date: str, commodity: str) -> list[MarketRecord]:
        """Parse OGD API response into validated MarketRecord objects."""
        # OGD field names vary — map common variants
        field_map = {
            "state": ["State_Name", "state", "State"],
            "district": ["District_Name", "district", "District"],
            "market": ["Market_Name", "market", "Market"],
            "variety": ["Variety", "variety"],
            "grade": ["Grade", "grade"],
            "min_price": ["Min_Price", "min_price", "Min Price"],
            "max_price": ["Max_Price", "max_price", "Max Price"],
            "modal_price": ["Modal_Price", "modal_price", "Modal Price"],
            "arrival_tonnes": ["Arrivals_in_Qtl", "arrival_tonnes", "Arrivals"],
        }

        def get_field(row: dict, field: str) -> str:
            for key in field_map.get(field, [field]):
                if key in row:
                    return str(row[key]).strip()
            return ""

        records: list[MarketRecord] = []
        for row in raw_records:
            try:
                arrival_raw = get_field(row, "arrival_tonnes")
                # OGD arrivals are in quintals; convert to tonnes (1 quintal = 0.1 tonne)
                arrival_tonnes = float(arrival_raw or 0) * 0.1

                record = MarketRecord(
                    state=get_field(row, "state"),
                    district=get_field(row, "district"),
                    market=get_field(row, "market"),
                    commodity=commodity,
                    variety=get_field(row, "variety"),
                    grade=get_field(row, "grade"),
                    min_price=float(get_field(row, "min_price") or 0),
                    max_price=float(get_field(row, "max_price") or 0),
                    modal_price=float(get_field(row, "modal_price") or 0),
                    arrival_tonnes=arrival_tonnes,
                    date=date,
                )
                records.append(record)
            except Exception as e:
                logger.debug("Skipping OGD record: %s | Error: %s", row, e)

        logger.info("Parsed %d valid records from OGD response", len(records))
        return records

    def fetch_market_data(self, date: str, commodity: str) -> list[MarketRecord]:
        resource_id = OGD_RESOURCE_IDS.get(commodity.lower())
        if not resource_id:
            logger.error("No OGD resource ID for commodity: %s", commodity)
            return []
        raw = self._call_ogd_api(resource_id, date)
        return self._parse_ogd_records(raw, date, commodity)

    def fetch_previous_day_data(self, date: str, commodity: str) -> list[MarketRecord]:
        from datetime import date as date_cls, timedelta
        prev_date = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
        return self.fetch_market_data(prev_date, commodity)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_provider() -> DataProvider:
    """Return the appropriate DataProvider based on PIPELINE_MODE config."""
    if PIPELINE_MODE == "live":
        logger.info("Using LiveProvider (OGD API)")
        return LiveProvider()
    else:
        logger.info("Using MockProvider (CSV fixtures in %s)", MOCK_DIR)
        return MockProvider()


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_commodity(date: str, commodity: str, provider: DataProvider) -> list[MarketRecord]:
    """
    Full ingestion flow for one commodity:
    1. Fetch from provider
    2. Store in SQLite (deduplication via ON CONFLICT IGNORE)
    3. Return records for downstream analytics
    """
    logger.info("Ingesting %s data for %s ...", commodity, date)

    records = provider.fetch_market_data(date, commodity)
    if not records:
        logger.warning("No records fetched for %s on %s", commodity, date)
        return []

    source = "mock" if isinstance(provider, MockProvider) else "ogd_api"
    inserted = insert_market_records(records, source=source)
    logger.info("Stored %d new records for %s (%s)", inserted, commodity, date)

    # Also ingest previous day data for delta computation
    prev_records = provider.fetch_previous_day_data(date, commodity)
    if prev_records:
        insert_market_records(prev_records, source=source)
        logger.debug("Stored %d previous-day records for %s", len(prev_records), commodity)

    return records
