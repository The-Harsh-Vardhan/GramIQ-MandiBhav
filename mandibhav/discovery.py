"""
mandibhav/discovery.py — Discovery-driven data ingestion layer and utilities.
"""

import csv
import logging
import re
import time
from datetime import date as date_cls, timedelta
from typing import Optional, Any

import requests

import config
from date_utils import normalize_date, parse_date

logger = logging.getLogger("mandibhav.discovery")


def get_field_val(row: dict, field: str) -> str:
    """Helper to extract values from OGD API or local CSV rows considering common variants."""
    field_map = {
        "state": ["State_Name", "state", "State"],
        "district": ["District_Name", "district", "District"],
        "market": ["Market_Name", "market", "Market"],
        "commodity": ["Commodity", "commodity"],
        "variety": ["Variety", "variety"],
        "grade": ["Grade", "grade"],
    }
    for key in field_map.get(field, [field]):
        if key in row:
            return str(row[key]).strip()
    return ""


def fetch_mock_raw_records(commodity_filter: Optional[str] = None) -> list[dict]:
    """Helper to load all raw records from local mock CSV files."""
    records = []
    commodities = ["soybean", "cotton"]
    if commodity_filter:
        c_lower = commodity_filter.lower()
        if "soy" in c_lower:
            commodities = ["soybean"]
        elif "cotton" in c_lower:
            commodities = ["cotton"]

    for comm in commodities:
        csv_path = config.MOCK_DIR / f"{comm}_sample.csv"
        if csv_path.exists():
            try:
                with open(csv_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        records.append(row)
            except Exception as e:
                logger.error("Failed to read mock CSV file %s: %s", csv_path, e)
    return records


def fetch_ogd_raw_records(
    date: Optional[str] = None,
    commodity_filter: Optional[str] = None,
    state_filter: Optional[str] = None,
    market_filter: Optional[str] = None,
    limit: int = 5000,
    timeout: Optional[tuple[float, float]] = None,
) -> list[dict]:
    """
    Fetches raw records from OGD API paginated, with optional filtering.
    """
    if getattr(config, "ogd_api_unreachable", False):
        logger.warning("OGD API is marked as unreachable. Bypassing OGD fetch.")
        return []

    api_key = config.OGD_API_KEY.strip()
    if not api_key:
        logger.warning("OGD_API_KEY is not set.")
        return []

    url = f"{config.OGD_API_BASE_URL}/{config.OGD_RESOURCE_ID}"
    headers = {
        "User-Agent": "GramIQ-MandiBhav/1.0.0 (https://gramiq.ai; contact@gramiq.ai)"
    }

    all_records = []
    offset = 0
    page_limit = 1000

    ogd_date = None
    if date:
        try:
            dt = parse_date(date)
            ogd_date = dt.strftime("%d/%m/%Y")
        except Exception as e:
            logger.error("Failed to parse date %s in OGD query: %s", date, e)
            return []

    while len(all_records) < limit:
        current_limit = min(page_limit, limit - len(all_records))
        params = {
            "api-key": api_key,
            "format": "json",
            "limit": current_limit,
            "offset": offset,
        }
        if ogd_date:
            params["filters[arrival_date]"] = ogd_date
        if commodity_filter:
            params["filters[commodity]"] = commodity_filter
        if state_filter:
            params["filters[state]"] = state_filter
        if market_filter:
            params["filters[market]"] = market_filter

        logger.debug(
            "OGD Discovery Fetch: URL=%s params=%s", url, params
        )

        timeout_val = timeout or (config.OGD_CONNECT_TIMEOUT, config.OGD_READ_TIMEOUT)
        max_attempts = 1 if timeout else 3
        success = False
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout_val,
                )
                if response.status_code == 200:
                    data = response.json()
                    records = data.get("records", [])
                    all_records.extend(records)
                    logger.debug(
                        "OGD Discovery Success: fetched %d records", len(records)
                    )
                    if len(records) < current_limit:
                        success = True
                        break
                    offset += current_limit
                    success = True
                    break
                else:
                    logger.warning(
                        "OGD Discovery attempt %d failed: HTTP %d",
                        attempt,
                        response.status_code,
                    )
            except requests.exceptions.RequestException as req_err:
                logger.warning(
                    "OGD Discovery attempt %d failed (connection/timeout): %s",
                    attempt,
                    req_err,
                )
                if attempt == max_attempts:
                    logger.error(
                        "OGD API is unreachable or timing out. Bypassing subsequent OGD queries."
                    )
                    config.ogd_api_unreachable = True
            except Exception as e:
                logger.warning(
                    "OGD Discovery attempt %d failed: %s", attempt, e
                )

            if attempt < max_attempts:
                time.sleep(1.0 * attempt)

        if not success or len(all_records) >= limit:
            break

    return all_records


def discover_metadata(limit: int = 5000, target_date: Optional[str] = None) -> dict:
    """
    Scans OGD (or mock) dataset for available metadata values.
    """
    if config.PIPELINE_MODE == "dev":
        raw_records = fetch_mock_raw_records()
    else:
        raw_records = fetch_ogd_raw_records(date=target_date, limit=limit)

    states = set()
    districts = set()
    markets = set()
    commodities = set()
    varieties = set()
    grades = set()

    for r in raw_records:
        s = get_field_val(r, "state")
        d = get_field_val(r, "district")
        m = get_field_val(r, "market")
        c = get_field_val(r, "commodity")
        v = get_field_val(r, "variety")
        g = get_field_val(r, "grade")

        if s: states.add(s)
        if d: districts.add(d)
        if m: markets.add(m)
        if c: commodities.add(c)
        if v: varieties.add(v)
        if g: grades.add(g)

    # Log results matching requested format
    logger.info(
        "Discovery complete\n\n"
        "States: %d\n"
        "Markets: %d\n"
        "Commodities: %d\n"
        "Varieties: %d\n"
        "Grades: %d",
        len(states),
        len(markets),
        len(commodities),
        len(varieties),
        len(grades),
    )

    return {
        "states": sorted(list(states)),
        "districts": sorted(list(districts)),
        "markets": sorted(list(markets)),
        "commodities": sorted(list(commodities)),
        "varieties": sorted(list(varieties)),
        "grades": sorted(list(grades)),
    }


def generate_availability_report(target_date: Optional[str] = None) -> dict:
    """
    Generates a report of what commodities and counts exist on target_date.
    """
    if not target_date:
        target_date = date_cls.today().isoformat()
    norm_date = normalize_date(target_date)

    if config.PIPELINE_MODE == "dev":
        raw_records = fetch_mock_raw_records()
    else:
        raw_records = fetch_ogd_raw_records(date=norm_date)

    counts = {}
    for r in raw_records:
        c = get_field_val(r, "commodity")
        if c:
            counts[c] = counts.get(c, 0) + 1

    return {
        "date": norm_date,
        "commodities": counts,
    }


def find_available_markets(commodity_slug: str, target_date: str) -> list[dict]:
    """
    Finds all markets listing commodity_slug on target_date.
    """
    norm_date = normalize_date(target_date)
    raw_records = []

    if config.PIPELINE_MODE == "dev":
        raw_records = fetch_mock_raw_records(commodity_slug)
    else:
        filter_values = config.OGD_COMMODITY_FILTERS.get(
            commodity_slug.lower(), [commodity_slug.title()]
        )
        for val in filter_values:
            records = fetch_ogd_raw_records(date=norm_date, commodity_filter=val)
            raw_records.extend(records)

    market_groups = {}
    for r in raw_records:
        state = get_field_val(r, "state")
        district = get_field_val(r, "district")
        market = get_field_val(r, "market")

        if not market:
            continue

        key = (state, district, market)
        market_groups[key] = market_groups.get(key, 0) + 1

    results = []
    for (state, district, market), count in market_groups.items():
        results.append(
            {
                "state": state,
                "district": district,
                "market": market,
                "records": count,
            }
        )

    # Sort descending by record count
    results.sort(key=lambda x: x["records"], reverse=True)
    return results


def select_market_from_list(
    markets: list[dict],
    preferred_market: Optional[str] = None,
    preferred_state: Optional[str] = None,
) -> Optional[dict]:
    """Helper to select best market according to Priority 1, 2, 3."""
    if not markets:
        return None

    # Sort a copy of the list by records descending to ensure we always operate on sorted data
    sorted_markets = sorted(markets, key=lambda x: x["records"], reverse=True)

    # Priority 1: User requested market exists today
    if preferred_market:
        pref_market_clean = (
            preferred_market.lower().replace("apmc", "").strip()
        )
        matched_markets = []
        for m in sorted_markets:
            m_name_clean = m["market"].lower().replace("apmc", "").strip()
            if (
                pref_market_clean in m_name_clean
                or m_name_clean in pref_market_clean
            ):
                matched_markets.append(m)
        if matched_markets:
            return matched_markets[0]

    # Priority 2: User requested state exists today
    if preferred_state:
        pref_state_lower = preferred_state.lower().strip()
        state_markets = [
            m for m in sorted_markets if pref_state_lower in m["state"].lower()
        ]
        if state_markets:
            return state_markets[0]

    # Priority 3: Commodity exists somewhere today
    return sorted_markets[0]


def find_latest_available_data(
    commodity_slug: str,
    preferred_market: Optional[str] = None,
    preferred_state: Optional[str] = None,
    target_date: Optional[str] = None,
) -> dict:
    """
    Search backward day-by-day (Today -> Yesterday -> Last 7 days)
    until records are found for commodity_slug.
    Checks the local database first for a fast path.
    """
    if getattr(config, "ogd_api_unreachable", False):
        logger.warning("OGD API is marked as unreachable. Skipping historical backward search.")
        return {}

    if not target_date:
        target_date = date_cls.today().isoformat()
    start_dt = parse_date(target_date)

    # 1. Fast Path: Check database first (SQLite or Supabase)
    from collections import defaultdict
    import supabase_backend

    if supabase_backend.enabled():
        try:
            found_date = supabase_backend.query_latest_date_before_or_equal(commodity_slug, target_date)
            if found_date:
                rows = supabase_backend.query_market_data(commodity_slug, found_date)
                if rows:
                    market_counts = defaultdict(int)
                    for r in rows:
                        state = r.get("state")
                        district = r.get("district")
                        market_name = r.get("market_name")
                        key = (state, district, market_name)
                        market_counts[key] += 1
                    
                    date_markets = []
                    for (state, district, market_name), count in market_counts.items():
                        date_markets.append({
                            "state": state,
                            "district": district,
                            "market": market_name,
                            "records": count
                        })
                    
                    selected = select_market_from_list(
                        date_markets,
                        preferred_market=preferred_market,
                        preferred_state=preferred_state
                    )
                    if selected:
                        logger.info("Found database historical match on date %s: %s, %s (%d records)", 
                                    found_date, selected["market"], selected["state"], selected["records"])
                        return {
                            "date": found_date,
                            "market": selected["market"],
                            "state": selected["state"],
                            "records": selected["records"]
                        }
        except Exception as e:
            logger.warning("Supabase database lookup for historical fallback failed: %s", e)
    elif config.DB_PATH.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(config.DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT market_date, state, district, market_name, COUNT(*) as count
                FROM market_data
                WHERE commodity_slug = ? AND market_date <= ?
                GROUP BY market_date, state, district, market_name
                ORDER BY market_date DESC, count DESC
            """
            rows = cursor.execute(query, (commodity_slug.lower(), target_date)).fetchall()
            conn.close()
            
            if rows:
                date_markets = defaultdict(list)
                for r in rows:
                    date_markets[r["market_date"]].append({
                        "state": r["state"],
                        "district": r["district"],
                        "market": r["market_name"],
                        "records": r["count"]
                    })
                
                # Check dates descending (latest first)
                sorted_dates = sorted(list(date_markets.keys()), reverse=True)
                for d in sorted_dates:
                    selected = select_market_from_list(
                        date_markets[d],
                        preferred_market=preferred_market,
                        preferred_state=preferred_state
                    )
                    if selected:
                        logger.info("Found database historical match on date %s: %s, %s (%d records)", 
                                    d, selected["market"], selected["state"], selected["records"])
                        return {
                            "date": d,
                            "market": selected["market"],
                            "state": selected["state"],
                            "records": selected["records"]
                        }
        except Exception as e:
            logger.warning("SQLite database lookup for historical fallback failed: %s", e)

    # 2. Slow Path: Search backward via OGD API (limited to 7 days for performance)
    for i in range(7):
        curr_dt = start_dt - timedelta(days=i)
        curr_date_str = curr_dt.strftime("%Y-%m-%d")

        logger.info(
            "Searching OGD API backward (Day %d/7): checking date %s...",
            i + 1,
            curr_date_str,
        )
        markets = find_available_markets(commodity_slug, curr_date_str)
        if markets:
            selected = select_market_from_list(
                markets,
                preferred_market=preferred_market,
                preferred_state=preferred_state,
            )
            if selected:
                logger.info(
                    "Historical OGD fallback found data on %s for %s (%s)",
                    curr_date_str,
                    selected["market"],
                    selected["state"],
                )
                return {
                    "date": curr_date_str,
                    "market": selected["market"],
                    "state": selected["state"],
                    "records": selected["records"],
                }

    logger.warning(
        "No historical records resolved for %s within database or recent OGD fallback search.",
        commodity_slug,
    )
    return {}


def select_demo_market(
    commodity_slug: str = "soybean",
    target_date: Optional[str] = None,
    preferred_market: Optional[str] = "Nagpur APMC",
    preferred_state: Optional[str] = "Maharashtra",
) -> dict:
    """
    Selects the best available market and date for a commodity demo using live OGD data.
    """
    if not target_date:
        target_date = date_cls.today().isoformat()
    norm_date = normalize_date(target_date)

    using_live = False
    records = []
    commodity_found = commodity_slug

    if config.PIPELINE_MODE == "dev":
        # Dev mode uses mock records directly (keep tests offline)
        records = fetch_mock_raw_records(commodity_slug)
        using_live = False
    else:
        # Fetch Soybean from OGD
        for val in config.OGD_COMMODITY_FILTERS.get("soybean", ["Soyabean", "Soybean"]):
            try:
                raw = fetch_ogd_raw_records(date=norm_date, commodity_filter=val, timeout=(2.0, 5.0))
                if raw:
                    records = raw
                    using_live = True
                    commodity_found = "soybean"
                    break
            except Exception as e:
                logger.warning("Failed to fetch OGD Soyabean records for %s on %s: %s", val, norm_date, e)

        # If no Soyabean records, try Cotton
        if not records:
            for val in config.OGD_COMMODITY_FILTERS.get("cotton", ["Cotton"]):
                try:
                    raw = fetch_ogd_raw_records(date=norm_date, commodity_filter=val, timeout=(2.0, 5.0))
                    if raw:
                        records = raw
                        using_live = True
                        commodity_found = "cotton"
                        break
                except Exception as e:
                    logger.warning("Failed to fetch OGD Cotton records for %s on %s: %s", val, norm_date, e)

        # If still no records, try fetching all commodities today
        if not records:
            try:
                raw = fetch_ogd_raw_records(date=norm_date, timeout=(2.0, 5.0))
                if raw:
                    records = raw
                    using_live = True
                    # Dynamically determine commodity from first record
                    comm_name = get_field_val(raw[0], "commodity").lower()
                    if "soy" in comm_name:
                        commodity_found = "soybean"
                    elif "cotton" in comm_name or "kapas" in comm_name:
                        commodity_found = "cotton"
                    else:
                        commodity_found = "soybean"
            except Exception as e:
                logger.warning("Failed to fetch OGD records today without filter: %s", e)

    # Logging based on data source
    if using_live:
        logger.info("Using LIVE OGD DATA")
    else:
        logger.info("Using MOCK DATA\nReason: OGD unavailable")
        # Fall back to MockProvider
        records = fetch_mock_raw_records(commodity_slug)
        commodity_found = commodity_slug

    # Select the first record with valid market and state
    selected_record = None
    if records:
        for r in records:
            if get_field_val(r, "market") and get_field_val(r, "state"):
                selected_record = r
                break
        if not selected_record:
            selected_record = records[0]

    if not selected_record:
        # Fallback to absolute defaults
        selected_market = "Nagpur APMC"
        selected_state = "Maharashtra"
        market_records_count = 0
    else:
        selected_market = get_field_val(selected_record, "market")
        selected_state = get_field_val(selected_record, "state")
        
        # Count records matching this market and state in our fetched list
        market_records_count = sum(
            1 for r in records
            if get_field_val(r, "market") == selected_market
            and get_field_val(r, "state") == selected_state
        )

    # Log in specific format
    logger.info("Found %d Soyabean records today.", len(records) if "soy" in commodity_found else 0)
    logger.info(
        "Selected:\n"
        "Market: %s\n"
        "State: %s",
        selected_market,
        selected_state
    )

    return {
        "date": norm_date,
        "market": selected_market,
        "state": selected_state,
        "records": market_records_count,
        "commodity": commodity_found
    }
