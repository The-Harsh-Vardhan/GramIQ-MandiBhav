# Implementation Plan — MandiBhav Date Standardization, Cleanup & Historical Backfill

This plan details the design and implementation steps to unify date handling, improve cleanup workflows, add a historical backfill mode, and make OGD request timeouts configurable.

## Root Cause Analysis
1. **Inconsistent Date Formats**: Different formats (e.g. YYYY-MM-DD vs DD/MM/YYYY) are used across OGD ingestion, SQLite DB storage, output folder names, sitemaps, and CLI inputs. This causes silent matching failures during database queries, cleanup operations, and page rendering.
2. **Brittle Cleanup Script**: `clear_date.py` only works for exact matching string formats, lacks options to target only database rows or only site cache, and reports success ambiguously even if no records were matched.
3. **Sparse Site Presentation**: The demo site only renders reports for a single targeted day, making it look empty. There is no historical archive navigation or range generation.
4. **Hardcoded timeouts**: Timeout values (10s and 15s) are hardcoded inside multiple API fetch blocks, which are not configurable for slow API conditions.

---

## Proposed Changes

### [Component: Shared Date Utility]

#### [NEW] [date_utils.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/date_utils.py)
- A dedicated date parsing and normalization module.
- Supports parsing:
  - `YYYY-MM-DD` / `YYYY/MM/DD`
  - `DD-MM-YYYY` / `MM-DD-YYYY` (hyphen-separated with MM/DD heuristics)
  - `DD/MM/YYYY` / `MM/DD/YYYY` (slash-separated with MM/DD heuristics)
- Exposes:
  - `parse_date(date_input) -> datetime.date`
  - `normalize_date(date_input) -> str` (returns standard `YYYY-MM-DD` string)
  - `is_valid_date(date_str) -> bool`

---

### [Component: Database Layer]

#### [MODIFY] [database.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/database.py)
- Import `normalize_date` from `date_utils`.
- Apply normalization on target date parameters in:
  - `insert_market_records` (for each record date)
  - `query_market_data`
  - `query_previous_day_data`
  - `insert_article`
  - `query_articles_by_date`
  - `log_pipeline_run`

---

### [Component: Ingestion & Timeout Configurations]

#### [MODIFY] [config.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/config.py)
- Load `OGD_CONNECT_TIMEOUT` (default: `10`) and `OGD_READ_TIMEOUT` (default: `45`) from environment.
- Log these values at startup.

#### [MODIFY] [ingestion.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/ingestion.py)
- Replace all hardcoded timeouts with `(config.OGD_CONNECT_TIMEOUT, config.OGD_READ_TIMEOUT)`.
- Use `normalize_date` to normalize requested target date parameters.
- Check if database already has records for a given date in `ingest_commodity` to skip redundant OGD API fetches, returning DB records immediately as `CACHE` source.

---

### [Component: Cleanup Script]

#### [MODIFY] [clear_date.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/clear_date.py)
- Import `normalize_date` to parse dates in any supported user format.
- Add CLI arguments:
  - `--dry-run`: Boolean flag.
  - `--all`: Removes matching DB rows, output folders, and cache files (default behavior).
  - `--cache-only`: Removes only site cache artifacts and outputs.
  - `--db-only`: Removes only database rows.
- Ensure that if nothing is deleted, it explicitly prints: `"0 records matched the requested date"`.

---

### [Component: Orchestration & Backfill Mode]

#### [MODIFY] [main.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py)
- Normalize target `--date` parameter at startup.
- Add backfill CLI arguments:
  - `--backfill-days`: Backfill N days ending at target date.
  - `--start-date` and `--end-date`: Backfill a range of dates.
- Loops through all resolved dates sequentially.
- If processing multiple dates, skip `stage_publish` inside the loop, running a single build and publish cycle at the end of the run for the latest date.
- Explicitly log whether the data source for each run was `LIVE`, `MOCK`, or `CACHE`.

---

### [Component: Static Site Generator & Templates]

#### [MODIFY] [build_site.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/build_site.py)
- Modify `discover_articles` to scan and aggregate articles from all date folders under `output/`.
- Update `article_url` and `article_file_path` to build date-based paths:
  - Non-latest articles are written to and linked as `site/{commodity}/{slug}/{date}/index.html`.
  - Latest articles are written to `site/{commodity}/{slug}/{date}/index.html` AND copied/written to root `site/{commodity}/{slug}/index.html`.
  - Support `hreflang` links grouped correctly for the same date.
- Update `render_commodity_pages` and `render_homepage` to filter article lists for the current/latest date, and generate an `archive_list` / `archive_dates` listing historical reports.

#### [MODIFY] [templates/site/commodity.html](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/templates/site/commodity.html)
- Add a beautiful `Historical Reports Archive` section showing past dates and links.

#### [MODIFY] [templates/site/homepage.html](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/templates/site/homepage.html)
- Add a quick navigation block to browse past dates.

---

### [Component: Documentation]

#### [NEW] [docs/data_management.md](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/docs/data_management.md)
- Explains date normalization rules.
- Explains cleanup procedures (including database-only and cache-only cleaning, and dry run safety).
- Explains backfill runs.
- Includes quick reference tables and commands.

---

## Verification Plan

### Automated Tests
- Run `pytest` to ensure all 50 existing tests continue to pass.
- Write new tests under `tests/test_date_management.py` to assert:
  - Date normalization correctness across formats.
  - Configurable timeouts are read correctly.
  - Cache checking / OGD skip logic works.

### Manual Verification
1. Run `python clear_date.py --date 05-06-2026 --dry-run` to preview cleanup.
2. Run `python main.py --mode demo --backfill-days 3 --date 2026-06-05 --skip-publish` to generate historical data.
3. Verify that the build site contains:
   - Archive folders like `site/soybean/nagpur/2026-06-03/index.html`.
   - Historical links on the homepage/commodity index.
   - Verified metadata in final json files.
