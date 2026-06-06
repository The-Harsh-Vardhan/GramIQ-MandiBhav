# Refactoring to Discovery-Based Live Data Ingestion

MandiBhav currently assumes specific geographic combinations exist in the OGD dataset (e.g., Maharashtra state and Nagpur APMC market). When OGD does not have records matching this assumption, the pipeline falls back to mock data even if live data exists elsewhere.

This plan shifts MandiBhav to a **discovery-driven architecture** where it inspects what data is actually available, selects the best active market dynamically, and uses historical back-searching if data isn't available for the target date.

## User Review Required

> [!IMPORTANT]
> The dynamic market selection will change the output article scope name in demo mode dynamically from just "Nagpur" to the actually discovered market (e.g. "Kukshi APMC" or "Latur"). 
> To prevent breaking downstream components (templates, validators, and translations) which hardcode or check the scope key `"soybean_nagpur"`, the scope key `"soybean_nagpur"` will be preserved, but the `market`, `scope_label`, and associated prices/arrivals in the payload will be dynamically populated.

> [!WARNING]
> Testing will be updated to handle the new pipeline modes. The test suite will be run to verify no regression.

## Open Questions

None. The requirements are fully detailed.

## Proposed Changes

---

### Ingestion & Discovery Component

We will create a new dataset discovery module, implement the availability report, remove the hardcoded geography filters in `ingestion.py`, and implement a historical fallback mechanism.

#### [NEW] [discovery.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/mandibhav/discovery.py)
* Create `mandibhav/discovery.py` to contain:
  * `discover_metadata(limit=5000, target_date=None) -> dict`: Fetches up to 5000 raw records (paginated), extracts unique states, districts, markets, commodities, varieties, and grades, and logs them.
  * `generate_availability_report(target_date) -> dict`: Returns a dictionary of commodity counts for the given date.
  * `find_available_markets(commodity_slug, target_date) -> list[dict]`: Groups records by state/district/market on the target date, returning them sorted by count.
  * `select_demo_market(commodity_slug, target_date, preferred_market, preferred_state) -> dict`: Evaluates the four priorities to select the best market and date, falling back historically if needed.
  * `find_latest_available_data(commodity_slug, preferred_market, preferred_state, target_date) -> dict`: Searches backward day-by-day (up to 30 days) to find the latest date with live data.

#### [MODIFY] [config.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/config.py)
* Add `"historical"` to the allowed/choices list of `PIPELINE_MODE`.
* Adjust `DEMO_MODE` to only be `True` when `PIPELINE_MODE == "demo"`.

#### [MODIFY] [ingestion.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/ingestion.py)
* Import discovery helpers.
* Update `LiveProvider.fetch_market_data`:
  * Remove hardcoded `"Maharashtra"` and `"Nagpur APMC"`.
  * In `demo` mode, use `config.demo_chosen_market` and `config.demo_chosen_state` as filters, querying only the chosen market to reduce OGD bandwidth.
  * If no records are found, log a descriptive diagnostic message:
    * `No {commodity} records found for {state} on {date}` or `No records found for requested market. Searching historical data...`
* Update `MockProvider.fetch_market_data` to filter using `config.demo_chosen_market` dynamically.
* Update `get_provider()` to return `LiveProvider` when `PIPELINE_MODE == "historical"`.

#### [MODIFY] [main.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py)
* Update CLI options to add `"historical"` as a choice for `--mode`.
* Update stage 1:
  * In `demo` mode, run `select_demo_market()` before ingestion.
  * Dynamically set `current_date` to the selected date and update `config.demo_chosen_market` / `config.demo_chosen_state`.
  * Clean up the old `query_latest_available_date` block.

---

### Command Line Tools

We will create three debug utility scripts inside a new `tools` directory.

#### [NEW] [discover.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/tools/discover.py)
* Simple CLI wrapper for `discover_metadata()`.

#### [NEW] [availability.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/tools/availability.py)
* Simple CLI wrapper for `generate_availability_report()`.

#### [NEW] [search_market.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/tools/search_market.py)
* CLI tool to search historical records matching a market name keyword (supporting both database and OGD queries).

---

### Tests

#### [MODIFY] [test_pipeline_optimization.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/tests/test_pipeline_optimization.py)
* Fix `test_write_article_file_uses_unique_review_filename` by monkeypatching `config.WRITE_ARTICLE_ARTIFACTS = True`.

#### [NEW] [test_discovery.py](file:///c:/D Drive/Projects/Summers%202026/GramIQ%20MandiBhav/tests/test_discovery.py)
* Add unit tests verifying `discover_metadata`, `generate_availability_report`, `find_available_markets`, `select_demo_market`, and `find_latest_available_data`.

## Verification Plan

### Automated Tests
Run the entire test suite including the new discovery tests:
```bash
pytest
```

### Manual Verification
Run the new tools and pipeline modes:
```bash
# Test discovery tools
python tools/discover.py
python tools/availability.py
python tools/search_market.py --market Nagpur

# Test live pipeline (no assumptions)
python main.py --mode live --skip-translate

# Test demo mode (automatic selection and fallback)
python main.py --mode demo --skip-translate
```
Confirm the console output displays accurate selection details, correct diagnostic logs, and that the run successfully generates the articles without failing on missing markets.
