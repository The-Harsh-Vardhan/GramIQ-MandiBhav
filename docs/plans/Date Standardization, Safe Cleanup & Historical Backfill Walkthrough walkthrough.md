# MandiBhav Date Standardization, Safe Cleanup & Historical Backfill Walkthrough

The MandiBhav by GramIQ pipeline has been successfully upgraded to standardize date handling across all layers (database, ingestion, caching, and CLI), implement a robust and safe data cleanup tool, and support historical data backfilling to populate the static website with historical reports.

---

## Changes Made

### 1. Standardized Date Handling
- **Shared Date Utility (`date_utils.py`)**: Created a dedicated module supporting various input formats (ISO `YYYY-MM-DD`, `YYYY/MM/DD`, `DD-MM-YYYY`, `MM-DD-YYYY`, `DD/MM/YYYY`, `MM/DD/YYYY`). Normalizes any valid input date to a standard `YYYY-MM-DD` string.
- **Database Layer (`database.py`)**: Normalized all queries and inputs in SQLite functions (inserts, queries, and logging) to standard `YYYY-MM-DD` to ensure query compatibility and data integrity.
- **Ingestion Layer (`ingestion.py`)**: Normalized requested date parameters and parsed dates returned from OGD API. Added database check at the start of `ingest_commodity` to skip OGD API queries if records already exist for the requested date, marking data source status as `CACHE`.
- **Configurable Timeouts**: Added `OGD_CONNECT_TIMEOUT` and `OGD_READ_TIMEOUT` to `config.py` and modified `ingestion.py` to use them for all request operations instead of hardcoded defaults.

### 2. Safe and Granular Cleanup Script (`clear_date.py`)
- Refactored to accept dates in any supported format and normalize them internally.
- Implemented targeted flags:
  - `--dry-run`: Previews matched items (database rows, output directory, cache files) without deleting.
  - `--db-only`: Clears database records only.
  - `--cache-only`: Clears generated files and cache files only.
  - `--all`: Clears everything (default).
- Explicitly outputs `"0 records matched the requested date"` if no data matches the targets.

### 3. Historical Backfill Mode (`main.py`)
- Added CLI options to main entry point:
  - `--backfill-days <N>`: Sequential backfill of `N` days ending at the target date.
  - `--start-date <DATE>` and `--end-date <DATE>`: Backfill range of dates.
- Loops through dates chronologically. If backfilling multiple days, it defers the static site generation and publishing to a single final build cycle at the end of the run.
- Logs the data source status (`LIVE`, `MOCK`, or `CACHE`) for each run.

### 4. Historical Site Aggregation (`build_site.py` & Templates)
- Updated `discover_articles` to scan and aggregate article JSON files across all date folders.
- Implemented `LATEST_DATES` mapping in `build_site.py` registry.
- Standardized `article_url` and `article_file_path` to build date-specific URLs (`/{commodity}/{slug}/{date}/`) and write copies to root paths (`/{commodity}/{slug}/`) only if it is the latest date.
- Modified templates (`commodity.html` and `homepage.html`) to display the dynamic historical archive navigation links.

---

## Verification & Testing

### Automated Unit Tests
Three new unit tests were added in `tests/test_date_management.py` to cover:
1. **`test_date_normalization`**: Verifies conversion of hyphen/slash formats to standardized `YYYY-MM-DD`.
2. **`test_ogd_timeouts_applied`**: Asserts that HTTP queries use `config.OGD_CONNECT_TIMEOUT` and `config.OGD_READ_TIMEOUT`.
3. **`test_db_cache_hit_bypass_ogd`**: Asserts that `ingest_commodity` skips OGD API query when database already has data for that date.

All **53 unit tests** are green and passing:
```text
tests/test_date_management.py::test_date_normalization PASSED
tests/test_date_management.py::test_ogd_timeouts_applied PASSED
tests/test_date_management.py::test_db_cache_hit_bypass_ogd PASSED

============================= 53 passed in 3.68s ==============================
```

### Manual Verification (End-to-End Backfill Run)
An end-to-end backfill demo run was executed:
```bash
python main.py --mode demo --backfill-days 3 --date 2026-06-05 --skip-publish
```

**Execution Output & Logs:**
- Successfully resolved date list: `['2026-06-03', '2026-06-04', '2026-06-05']`.
- Skipped redundant OGD API fetches on successive iterations due to database cache hits.
- Deferred static site generation until the end of the backfill loop.
- Built a multi-date website structure containing root indices and nested date subdirectories:
  - `site/soybean/nagpur/index.html` (root/latest copy)
  - `site/soybean/nagpur/2026-06-03/index.html` (June 3 archive)
  - `site/soybean/nagpur/2026-06-04/index.html` (June 4 archive)
  - `site/soybean/nagpur/2026-06-05/index.html` (June 5 archive)
- Verified sitemap, RSS feed, and search indexes correctly index the new archive URLs.
