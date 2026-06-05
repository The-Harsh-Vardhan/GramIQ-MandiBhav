"""
ingestion.py — DataProvider abstraction with MockProvider and LiveProvider.

Usage:
    from ingestion import get_provider
    provider = get_provider(config)
    records = provider.fetch_market_data("2026-06-04", "soybean")
"""

import csv
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import requests

import config
from config import (
    PIPELINE_MODE, MOCK_DIR, OGD_API_KEY, OGD_API_BASE_URL, OGD_RESOURCE_ID,
    OGD_API_FORMAT, OGD_PAGE_LIMIT, OGD_COMMODITY_FILTERS,
)
from schemas import MarketRecord
from database import insert_market_records
from date_utils import normalize_date, parse_date

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
                    logger.warning("Skipped record due to validation failure on Row %d in %s: %s", i, csv_path.name, e)

        logger.info("MockProvider: loaded %d records from %s", len(records), csv_path.name)
        return records

    def fetch_market_data(self, date: str, commodity: str) -> list[MarketRecord]:
        config.ingestion_data_source = "MOCK"
        csv_path = self.mock_dir / f"{commodity}_sample.csv"
        records = self._load_csv(csv_path, override_date=date)
        if getattr(config, "DEMO_MODE", False):
            nagpur_records = [r for r in records if "nagpur" in r.market.lower()]
            if nagpur_records:
                config.demo_chosen_market = "Nagpur"
                return nagpur_records
            elif records:
                config.demo_chosen_market = records[0].market
                return [records[0]]
        return records

    def fetch_previous_day_data(self, date: str, commodity: str) -> list[MarketRecord]:
        # Compute the previous date from the requested date
        date = normalize_date(date)
        from datetime import timedelta
        prev_date = (parse_date(date) - timedelta(days=1)).strftime("%Y-%m-%d")
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

    # Placeholder strings that indicate the key was never set
    _PLACEHOLDER_KEYS = {"your_ogd_api_key_here", "", "none", "null"}

    def __init__(
        self,
        api_key: str = OGD_API_KEY,
        endpoint: str = OGD_API_BASE_URL,
        resource_id: str = OGD_RESOURCE_ID,
    ):
        self.api_key = api_key.strip() if api_key else ""
        self.endpoint = endpoint.strip() if endpoint else ""
        self.resource_id = resource_id.strip() if resource_id else ""
        self.validate_config()
        if getattr(config, "DEBUG_OGD_SCHEMA", False):
            self.run_schema_discovery()

    def run_schema_discovery(self) -> None:
        """Fetch OGD records without filters to print/validate schema."""
        logger.info("[SCHEMA DISCOVERY] Starting schema discovery mode...")
        url = f"{self.endpoint}/{self.resource_id}"
        params = {
            "api-key": self.api_key,
            "format": OGD_API_FORMAT,
            "limit": 5,
        }
        headers = {
            "User-Agent": "GramIQ-MandiBhav/1.0.0 (https://gramiq.ai; contact@gramiq.ai)"
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=(config.OGD_CONNECT_TIMEOUT, config.OGD_READ_TIMEOUT))
            if response.status_code == 200:
                data = response.json()
                records = data.get("records", [])
                if records:
                    first_record = records[0]
                    logger.info("[SCHEMA DISCOVERY] First record: %s", first_record)
                    field_names = list(first_record.keys())
                    logger.info("[SCHEMA DISCOVERY] Field names in response records: %s", field_names)
                    
                    fields_to_validate = ["Arrival_Date", "commodity", "Commodity", "arrival_date"]
                    for f in fields_to_validate:
                        is_present = f in field_names
                        logger.info("[SCHEMA DISCOVERY] Field '%s' validation: %s", f, "VALID/PRESENT" if is_present else "INVALID/NOT PRESENT")
                else:
                    logger.warning("[SCHEMA DISCOVERY] No records returned.")
            else:
                logger.error("[SCHEMA DISCOVERY] Request failed with status code: %d", response.status_code)
        except Exception as e:
            logger.error("[SCHEMA DISCOVERY] Error during discovery: %s", e)

    def validate_config(self) -> None:
        """Validate the OGD configuration parameters. Raises ValueError if invalid."""
        import re

        # 1. API key presence validation
        if not self.api_key or self.api_key.lower() in self._PLACEHOLDER_KEYS:
            raise ValueError(
                "OGD_API_KEY is not configured. "
                "Set a valid key in .env or switch to PIPELINE_MODE=dev."
            )

        # 2. Endpoint format (should start with http:// or https://)
        if not self.endpoint:
            raise ValueError("OGD API endpoint is missing or empty.")
        if not (self.endpoint.startswith("http://") or self.endpoint.startswith("https://")):
            raise ValueError(f"OGD API endpoint must start with http:// or https:// (got '{self.endpoint}')")

        # 3. Resource ID format (should be a valid UUID format)
        if not self.resource_id:
            raise ValueError("OGD Resource ID is missing or empty.")
        uuid_pattern = r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
        if not re.match(uuid_pattern, self.resource_id.lower()):
            raise ValueError(f"OGD Resource ID must be a valid UUID format (got '{self.resource_id}')")

    def _call_ogd_api_page(
        self,
        date: Optional[str],
        commodity_filter: Optional[str],
        offset: int,
        limit: int,
        state_filter: Optional[str] = None,
        market_filter: Optional[str] = None,
    ) -> list[dict]:
        """Make one paginated OGD API request and return raw records."""
        import time
        from datetime import date as date_cls
        from config import DEBUG_INGESTION

        params = {
            "api-key": self.api_key,
            "format": OGD_API_FORMAT,
            "offset": offset,
            "limit": limit,
        }
        if date:
            d = date_cls.fromisoformat(date)
            ogd_date = d.strftime("%d/%m/%Y")
            params["filters[arrival_date]"] = ogd_date
        else:
            ogd_date = "None"

        if commodity_filter:
            params["filters[commodity]"] = commodity_filter

        if state_filter:
            params["filters[state]"] = state_filter

        if market_filter:
            params["filters[market]"] = market_filter

        url = f"{self.endpoint}/{self.resource_id}"
        
        # Use custom User-Agent to prevent the OGD server from dropping/timing out requests
        headers = {
            "User-Agent": "GramIQ-MandiBhav/1.0.0 (https://gramiq.ai; contact@gramiq.ai)"
        }
        timeout_val = (config.OGD_CONNECT_TIMEOUT, config.OGD_READ_TIMEOUT)

        # Detailed Logging before request: Endpoint, Resource ID, Commodity, Date, Limit, Timeout
        logger.info(
            "Fetching OGD data:\n"
            "  Endpoint: %s\n"
            "  Resource ID: %s\n"
            "  Commodity: %s\n"
            "  Date: %s (OGD=%s)\n"
            "  Limit: %d\n"
            "  Timeout: %s",
            self.endpoint, self.resource_id, commodity_filter, date, ogd_date, limit, str(timeout_val)
        )

        if DEBUG_INGESTION:
            logger.info("[DEBUG] Request URL: %s", url)
            logger.info("[DEBUG] Query Parameters: %s", params)

        max_attempts = 4  # 1 initial attempt + 3 retries
        backoff = 1.0

        for attempt in range(1, max_attempts + 1):
            t_start = time.time()
            try:
                response = requests.get(url, params=params, headers=headers, timeout=timeout_val)
                elapsed = time.time() - t_start
                status_code = response.status_code

                # Non-200 responses
                if status_code != 200:
                    logger.error(
                        "OGD API attempt %d failed: Status Code=%d | Response Time=%.2fs",
                        attempt, status_code, elapsed
                    )
                    response.raise_for_status()

                # If successful
                try:
                    data = response.json()
                except ValueError as json_err:
                    logger.error(
                        "OGD API attempt %d returned invalid JSON: Response Time=%.2fs | Error: %s",
                        attempt, elapsed, json_err
                    )
                    raise ValueError(f"Invalid JSON response from OGD API: {json_err}")

                # Check if it returned {"message": "ERRORS"} or similar error structures
                if "records" not in data:
                    message = data.get("message", "No 'records' field in response JSON")
                    logger.error(
                        "OGD API attempt %d failed: Response Time=%.2fs | Error message: %s",
                        attempt, elapsed, message
                    )
                    raise ValueError(f"OGD API returned error response: {message}")

                records = data.get("records", [])

                # Detailed Logging after request: Status Code, Response Time, Record Count
                logger.info(
                    "OGD API SUCCESS:\n"
                    "  Status Code: %d\n"
                    "  Response Time: %.2fs\n"
                    "  Record Count: %d",
                    status_code, elapsed, len(records)
                )

                if DEBUG_INGESTION:
                    raw_text = response.text
                    snippet = raw_text[:500] + ("..." if len(raw_text) > 500 else "")
                    logger.info("[DEBUG] First Response Snippet: %s", snippet)

                return records

            except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError) as e:
                elapsed = time.time() - t_start
                exc_type = type(e).__name__
                exc_msg = str(e)

                # Detailed Logging if failure: Exception Type, Exception Message
                logger.error(
                    "OGD API request failed on attempt %d:\n"
                    "  Exception Type: %s\n"
                    "  Exception Message: %s\n"
                    "  Response Time: %.2fs",
                    attempt, exc_type, exc_msg, elapsed
                )

                # Determine retry conditions: ONLY Timeout, Connection errors, or 5xx HTTP errors
                should_retry = False
                if isinstance(e, (requests.Timeout, requests.ConnectionError)):
                    should_retry = True
                elif isinstance(e, requests.HTTPError) and e.response is not None:
                    if 500 <= e.response.status_code < 600:
                        should_retry = True

                # Do NOT retry for 401, 403, or invalid resource ID
                if should_retry and attempt < max_attempts:
                    logger.warning(
                        "Retrying request (Retry %d of 3) in %.1fs...",
                        attempt, backoff
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise e

        return []

    def _fetch_all_pages(
        self,
        date: Optional[str],
        commodity_filter: Optional[str],
        limit: Optional[int] = None,
        state_filter: Optional[str] = None,
        market_filter: Optional[str] = None,
    ) -> list[dict]:
        """Fetch all pages for one commodity filter value."""
        all_records: list[dict] = []
        offset = 0
        
        from config import DEBUG_INGESTION
        if limit is not None:
            page_limit = limit
        elif DEBUG_INGESTION:
            # Use limit=10 during debugging to avoid loading excessive data
            page_limit = 10
        else:
            page_limit = OGD_PAGE_LIMIT

        page_num = 0
        while True:
            page_num += 1
            page = self._call_ogd_api_page(
                date=date,
                commodity_filter=commodity_filter,
                offset=offset,
                limit=page_limit,
                state_filter=state_filter,
                market_filter=market_filter,
            )
            if not page:
                break
            all_records.extend(page)
            if len(page) < page_limit:
                break
            if getattr(config, "PIPELINE_MODE", "demo") == "demo":
                if len(all_records) > 20 or page_num >= 3:
                    logger.info("Demo Mode: reached pagination limits (records: %d, pages: %d)", len(all_records), page_num)
                    break
            offset += page_limit

        return all_records

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

                # Parse raw date from the record if it exists and differs
                raw_date = row.get("arrival_date", row.get("Arrival_Date", ""))
                record_date = date
                if raw_date:
                    raw_date_str = str(raw_date).strip()
                    parsed_date = None
                    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                        try:
                            from datetime import datetime
                            parsed_dt = datetime.strptime(raw_date_str, fmt)
                            parsed_date = parsed_dt.strftime("%Y-%m-%d")
                            break
                        except Exception:
                            continue
                    if parsed_date:
                        record_date = parsed_date
                        logger.debug(
                            "Raw OGD Date: %s | Parsed Date: %s | Stored Date: %s",
                            raw_date_str, parsed_date, record_date
                        )
                    else:
                        logger.warning("Could not parse OGD Date: %s, falling back to %s", raw_date_str, date)

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
                    date=record_date,
                )
                records.append(record)
            except Exception as e:
                logger.warning("Skipped record due to validation failure on OGD record: %s | Error: %s", row, e)

        logger.info("Parsed %d valid records from OGD response", len(records))
        return records

    def fetch_market_data(self, date: str, commodity: str, limit: Optional[int] = None) -> list[MarketRecord]:
        date = normalize_date(date)
        config.ingestion_data_source = "LIVE"
        commodity_key = commodity.lower()
        filter_values = OGD_COMMODITY_FILTERS.get(commodity_key, [commodity.title()])
        all_raw: list[dict] = []

        if getattr(config, "PIPELINE_MODE", "demo") == "demo":
            # Nagpur Demo Mode Ingestion
            logger.info("Demo Mode: Fetching Soybean live data for Maharashtra...")
            state_filter = "Maharashtra"
            # Try Nagpur APMC direct filter first
            for commodity_filter in filter_values:
                raw = self._fetch_all_pages(
                    date=date,
                    commodity_filter=commodity_filter,
                    limit=limit,
                    state_filter=state_filter,
                    market_filter="Nagpur APMC"
                )
                if raw:
                    logger.info("Demo Mode: Direct market filter found %d records for Nagpur APMC", len(raw))
                    all_raw = raw
                    break
            
            # If Nagpur direct filter yielded nothing, fetch all Maharashtra soybean records and filter locally
            if not all_raw:
                logger.info("Demo Mode: Direct Nagpur query returned 0 records. Fetching all Maharashtra Soybean records for local filtering.")
                maharashtra_raw = []
                for commodity_filter in filter_values:
                    raw = self._fetch_all_pages(
                        date=date,
                        commodity_filter=commodity_filter,
                        limit=limit,
                        state_filter=state_filter
                    )
                    if raw:
                        maharashtra_raw = raw
                        break
                
                if maharashtra_raw:
                    # Implement fallback priority logic: Nagpur -> Amravati -> Wardha -> Any Maharashtra market
                    fallbacks = ["nagpur", "amravati", "wardha"]
                    chosen_market = None
                    for market_keyword in fallbacks:
                        matched = [
                            r for r in maharashtra_raw
                            if market_keyword in str(r.get("Market_Name") or r.get("market") or "").lower()
                        ]
                        if matched:
                            all_raw = matched
                            chosen_market = matched[0].get("Market_Name") or matched[0].get("market") or market_keyword.title()
                            logger.info("Demo Mode: Found local match for keyword '%s' -> Chosen market: %s (%d records)", market_keyword, chosen_market, len(matched))
                            break
                    
                    if not all_raw:
                        # Fallback to any Maharashtra market
                        markets_found = set(str(r.get("Market_Name") or r.get("market") or "") for r in maharashtra_raw if (r.get("Market_Name") or r.get("market")))
                        if markets_found:
                            chosen_market = sorted(list(markets_found))[0]
                            all_raw = [
                                r for r in maharashtra_raw
                                if str(r.get("Market_Name") or r.get("market") or "").lower() == chosen_market.lower()
                            ]
                            logger.info("Demo Mode: Fallback to first available Maharashtra market: %s (%d records)", chosen_market, len(all_raw))
            
            # Store chosen market name in config for Problem 10 logging
            if all_raw:
                chosen = all_raw[0].get("Market_Name") or all_raw[0].get("market") or "Nagpur APMC"
                # Strip APMC suffix for display
                chosen_clean = re.sub(r"\s+apmc\b", "", chosen, flags=re.IGNORECASE).strip()
                config.demo_chosen_market = chosen_clean
            else:
                config.demo_chosen_market = "Nagpur"

            if not all_raw:
                logger.warning("Demo Mode: No live OGD data found for Nagpur/fallback markets. Falling back to MockProvider.")
                config.ingestion_data_source = "MOCK"
                mock_provider = MockProvider()
                mock_records = mock_provider.fetch_market_data(date, commodity)
                config.demo_chosen_market = "Nagpur"
                return mock_records
        else:
            # --- Step 1: Date + Commodity ---
            logger.info("Attempting Query 1: date + commodity filter for %s on %s", commodity, date)
            for commodity_filter in filter_values:
                if limit is not None:
                    raw = self._fetch_all_pages(date, commodity_filter, limit)
                else:
                    raw = self._fetch_all_pages(date, commodity_filter)
                if raw:
                    logger.info("Query 1 SUCCESS: Found %d records for commodity filter '%s'", len(raw), commodity_filter)
                    all_raw = raw
                    break

            # --- Step 2: Commodity Only ---
            if not all_raw:
                logger.info("Query 1 returned 0 records. Attempting Query 2: commodity filter only for %s", commodity)
                for commodity_filter in filter_values:
                    if limit is not None:
                        raw = self._fetch_all_pages(None, commodity_filter, limit)
                    else:
                        raw = self._fetch_all_pages(None, commodity_filter)
                    if raw:
                        logger.info("Query 2 SUCCESS: Found %d records for commodity filter '%s'", len(raw), commodity_filter)
                        all_raw = raw
                        break

            # --- Step 3: Latest Records (no filters) ---
            if not all_raw:
                logger.info("Query 2 returned 0 records. Attempting Query 3: latest records (no filters)")
                if limit is not None:
                    raw = self._fetch_all_pages(None, None, limit)
                else:
                    raw = self._fetch_all_pages(None, None, 100)
                if raw:
                    logger.info("Query 3 SUCCESS: Found %d latest raw records from OGD API", len(raw))
                    # Filter locally for commodity
                    filtered_raw = []
                    for row in raw:
                        row_commodity = str(row.get("commodity", "")).strip().lower()
                        for field_name in ["commodity", "Commodity"]:
                            if field_name in row:
                                row_commodity = str(row[field_name]).strip().lower()
                                break
                        if any(fv.lower() == row_commodity for fv in filter_values):
                            filtered_raw.append(row)
                    if filtered_raw:
                        logger.info("Filtered Query 3: Found %d records matching commodity %s", len(filtered_raw), commodity)
                        all_raw = filtered_raw
                    else:
                        logger.warning("Query 3 returned records, but none matched commodity %s", commodity)

            # --- Step 4: Fallback to Mock ---
            if not all_raw:
                logger.warning("All OGD API queries returned 0 records for %s on %s. Falling back to MockProvider.", commodity, date)
                config.ingestion_data_source = "MOCK"
                mock_provider = MockProvider()
                return mock_provider.fetch_market_data(date, commodity)

        return self._parse_ogd_records(all_raw, date, commodity)

    def fetch_previous_day_data(self, date: str, commodity: str) -> list[MarketRecord]:
        from datetime import timedelta
        norm_date = normalize_date(date)
        prev_date = (parse_date(norm_date) - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.fetch_market_data(prev_date, commodity)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_provider() -> DataProvider:
    """
    Return the appropriate DataProvider based on PIPELINE_MODE.
    If PIPELINE_MODE=live but OGD_API_KEY is missing/invalid,
    logs a clear warning and falls back to MockProvider automatically.
    """
    if PIPELINE_MODE in ("live", "demo"):
        try:
            provider = LiveProvider()
            logger.info("Using LiveProvider (OGD API)")
            return provider
        except ValueError as e:
            logger.warning(
                "LiveProvider unavailable: %s — falling back to MockProvider.", e
            )
    logger.info("Using MockProvider (CSV fixtures in %s)", MOCK_DIR)
    return MockProvider()


# ---------------------------------------------------------------------------
# API Connectivity Test
# ---------------------------------------------------------------------------

def test_connection() -> dict:
    """
    Test API connectivity to OGD India.
    Verifies config validity and attempts to fetch exactly 1 record.
    Returns:
        {
          "success": bool,
          "status_code": int,
          "records": int,
          "error": str | None
        }
    """
    try:
        provider = LiveProvider()
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "records": 0,
            "error": f"Configuration Validation Failed: {e}"
        }

    import time
    url = f"{provider.endpoint}/{provider.resource_id}"
    params = {
        "api-key": provider.api_key,
        "format": OGD_API_FORMAT,
        "limit": 1
    }
    headers = {
        "User-Agent": "GramIQ-MandiBhav/1.0.0 (https://gramiq.ai; contact@gramiq.ai)"
    }

    t_start = time.time()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=(config.OGD_CONNECT_TIMEOUT, config.OGD_READ_TIMEOUT))
        elapsed = time.time() - t_start
        status_code = response.status_code

        if status_code == 200:
            data = response.json()
            if "records" in data:
                return {
                    "success": True,
                    "status_code": status_code,
                    "records": len(data["records"]),
                    "error": None
                }
            else:
                error_msg = data.get("message", "No 'records' field in response JSON")
                return {
                    "success": False,
                    "status_code": status_code,
                    "records": 0,
                    "error": f"OGD API returned error message: {error_msg}"
                }
        else:
            return {
                "success": False,
                "status_code": status_code,
                "records": 0,
                "error": f"HTTP error status {status_code}"
            }
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "records": 0,
            "error": f"Connection Failed: {type(e).__name__} — {e}"
        }


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_commodity(date: str, commodity: str, provider: DataProvider) -> list[MarketRecord]:
    """
    Full ingestion flow for one commodity:
    1. Fetch from provider; if live fetch fails, automatically retry with MockProvider
    2. Store in SQLite (deduplication via ON CONFLICT IGNORE)
    3. Return records for downstream analytics
    """
    norm_date = normalize_date(date)
    logger.info("Ingesting %s data for %s ...", commodity, norm_date)

    import database
    db_records = database.query_market_data(commodity, norm_date)
    if db_records:
        logger.info("Database cache hit for %s on %s. Skipping OGD API query.", commodity, norm_date)
        config.ingestion_data_source = "CACHE"
        records = []
        for r in db_records:
            try:
                records.append(
                    MarketRecord(
                        state=r["state"],
                        district=r.get("district", ""),
                        market=r["market_name"],
                        commodity=r["commodity_slug"],
                        variety=r.get("variety", ""),
                        grade=r.get("grade", ""),
                        min_price=r["min_price"],
                        max_price=r["max_price"],
                        modal_price=r["modal_price"],
                        arrival_tonnes=r["arrival_tonnes"],
                        date=r["market_date"]
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse DB record as MarketRecord: %s | Error: %s", r, e)
        if records:
            config.demo_records_count = len(records)
            return records

    records = []
    actual_provider = provider

    try:
        records = provider.fetch_market_data(date, commodity)
    except Exception as e:
        if not isinstance(provider, MockProvider):
            logger.warning("Live provider unavailable")
            logger.warning("Switching to mock mode")
            logger.warning("Reason: %s", e)
            actual_provider = MockProvider()
            try:
                records = actual_provider.fetch_market_data(date, commodity)
            except Exception as fallback_err:
                logger.error("MockProvider also failed for %s: %s", commodity, fallback_err)
                return []
        else:
            logger.error("MockProvider failed for %s: %s", commodity, e)
            return []

    if not records:
        logger.warning("No records fetched for %s on %s", commodity, date)
        config.demo_records_count = 0
        return []

    config.demo_records_count = len(records)

    source = "mock" if isinstance(actual_provider, MockProvider) else "ogd_api"
    inserted = insert_market_records(records, source=source)
    logger.info("Stored %d new records for %s (%s)", inserted, commodity, date)

    # Also ingest previous day data for delta computation
    try:
        prev_records = actual_provider.fetch_previous_day_data(date, commodity)
        if prev_records:
            insert_market_records(prev_records, source=source)
            logger.debug(
                "Stored %d previous-day records for %s", len(prev_records), commodity
            )
    except Exception as e:
        logger.warning("Previous-day ingestion failed for %s (non-fatal): %s", commodity, e)

    return records
