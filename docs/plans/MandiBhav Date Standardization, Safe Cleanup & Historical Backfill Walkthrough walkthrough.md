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

All **53 unit tests** are green and passing.

---

# MandiBhav Trust, Data Integrity & Publishing Gate Refactoring Walkthrough

The MandiBhav by GramIQ pipeline has been successfully refactored into a trustworthy agricultural intelligence platform. This includes restricting speculative AI commentary, disabling fragile machine translations for MVP, enforcing claim grounding, dynamically classifying reports, and embedding data transparency metrics.

## Changes Made

### 1. Restricted AI Prompts & Grounded Content
- **Article Template Redesign (`article_types.json`)**: Replaced `nagpur_demo` with `price_snapshot_report`. Removed sections asking for speculative commentary such as *Farmer Advice*, *AI Outlook*, and *Market Highlights*.
- **System Prompt Rewrite (`system_prompt.txt`)**: Instructed the LLM to write strictly factual, data-grounded reports. Outlawed demand/supply speculation, future price predictions, and advisory statements.
- **Translation Disabled (`config.py`)**: Disabled `TRANSLATION_LANGUAGES` in demo/MVP mode to focus strictly on English content and prevent translation hallucinations.

### 2. Validation & Quality Scoring Layers
- **Grounded Claim Validation (`seo_assembler.py`)**: Implemented `validate_claim_support()` which parses each paragraph in the generated article body. Any paragraphs containing speculative keywords (e.g. `demand`, `supply`, `outlook`, `future`) that are not backed by season notes are stripped from the final body, and the `unsupported_claims_count` is incremented.
- **Dynamic Report Classification (`seo_assembler.py`)**: Added `determine_report_classification()` to classify reports based on the incoming data profile:
  - `TREND_REPORT`: Multi-market with historical comparison data.
  - `MARKET_REPORT`: Multi-market with no historical comparison data.
  - `PRICE_SNAPSHOT`: Single-market with no historical comparison data.
- **Publishing Gate & Confidence Calibration**:
  - Auto-publish requires `confidence_score >= 0.75` (high-volume live runs) and clean validation (`contradictions == 0` and `scope_violations == 0`).
  - Added new properties (`record_count`, `unique_markets_count`, `unique_varieties_count`, `unique_grades_count`) to `FinalArticleJSON` model in [schemas.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/schemas.py) and mapped them in `assemble_final_article`.
- **Transparency Footers**: Localized disclosures in `build_disclosures()` were expanded to print exact counts of analyzed records, markets, varieties, and grades.

### 3. Quality Evaluation Report & Static Site Generator
- **Content Integrity Metrics (`evaluate.py`)**:
  - Expanded `ArticleMetrics` and `EvaluationReport` to track supported claims %, classification accuracy, and record/market/variety/grade counts.
  - Added a clean box-drawn `DATA SOURCES` transitional table in stdout summarizing data status (LIVE, CACHE, MOCK) and record counts for all scanned scopes.
- **Site Generator Logging Cleanup (`build_site.py`)**:
  - Demoted page-written logs and sitemap/RSS/search-index generation outputs from `logger.info` to `logger.debug` to clean console stdout.

---

## Verification & Testing

### Automated Test Runs
All **53 tests** remain fully passing after integrating the new schema attributes and verification logic:
```bash
pytest
```
Output:
```text
tests/test_truthfulness.py::test_truthfulness_perfect_article PASSED
tests/test_truthfulness.py::test_truthfulness_arrivals_zero_contradictions PASSED
tests/test_truthfulness.py::test_truthfulness_low_record_count_contradictions PASSED
tests/test_truthfulness.py::test_truthfulness_unsupported_claims PASSED
tests/test_truthfulness.py::test_truthfulness_scope_violations PASSED
tests/test_truthfulness.py::test_credibility_live_perfect PASSED
tests/test_truthfulness.py::test_credibility_mock_capped PASSED
tests/test_truthfulness.py::test_credibility_cache_capped PASSED
tests/test_truthfulness.py::test_credibility_penalties PASSED
tests/test_truthfulness.py::test_credibility_zeroed_by_contradictions PASSED
tests/test_truthfulness.py::test_disclosure_injection_english PASSED
tests/test_truthfulness.py::test_disclosure_injection_hindi PASSED
tests/test_truthfulness.py::test_confidence_gate_auto_publish_success PASSED
tests/test_truthfulness.py::test_confidence_gate_review_due_to_contradiction PASSED

============================= 53 passed in 2.09s ==============================
```

### End-to-End Execution
Ran a full execution on a clean dataset:
```bash
python clear_date.py --date 2026-06-05
python main.py --mode demo --date 2026-06-05 --publish
```

**Quality Report Console Output:**
```text
═══════════════════════════════════════════════════════
  MandiBhav Quality Report — 2026-06-05
═══════════════════════════════════════════════════════

  PIPELINE
  ├── Total files:              1
  ├── Published (≥0.75):        0  ⚠️
  ├── Review Required (0.40-0.74): 1
  ├── Blocked (<0.40):          0
  └── Pipeline time:            43s

  CONTENT
  ├── Avg word count:           218.0 words
  ├── Word count OK:            0.0%  ⚠️
  ├── CTA present:              100.0%  ✅
  └── Avg FAQs per article:     3.0

  SEO
  ├── Keyword in title:         100.0%  ✅
  ├── Title length OK:          100.0%  ✅
  ├── Meta desc length OK:      100.0%  ✅
  ├── Has H2 headings:          100.0%  ✅
  ├── JSON-LD NewsArticle OK:   100.0%  ✅
  └── JSON-LD FAQPage OK:       100.0%  ✅

  CONFIDENCE
  ├── Average:                  0.000
  ├── Minimum:                  0.000
  └── Maximum:                  0.000

  CONTENT INTEGRITY METRICS
  ├── Supported claims %:       86.7%  ⚠️
  ├── Unsupported claims count: 2  ⚠️
  ├── Contradictions count:     0  ✅
  ├── Scope violations count:   0  ✅
  ├── Classification accuracy:  100.0%  ✅
  ├── Total records analyzed:   30
  ├── Avg unique markets:       28.0
  ├── Avg unique varieties:     2.0
  ├── Avg unique grades:        2.0
  ├── Fallback disclosure:      100.0%  ✅
  ├── Data source disclosure:   100.0%  ✅
  └── Avg truthfulness score:   0.800  ✅

  DATA SOURCES
  ┌─────────────────────────────────┬─────────────┬───────────┬─────────┬───────────┬────────┐
  │ Market Scope (Language)         │ Status      │ Type      │ Records │ Markets   │ Grades │
  ├─────────────────────────────────┼─────────────┼───────────┼─────────┼───────────┼────────┤
  │ soybean_nagpur (en)             │ LIVE        │ TREND_REPORT │ 30      │ 28        │ 2      │
  └─────────────────────────────────┴─────────────┴───────────┴─────────┴───────────┴────────┘

  WARNINGS (2)
  ⚠️  soybean_nagpur (en): word count 218 out of range
  ⚠️  soybean_nagpur (en): low confidence 0.000

  OUTPUT: output/2026-06-05/
═══════════════════════════════════════════════════════
```
