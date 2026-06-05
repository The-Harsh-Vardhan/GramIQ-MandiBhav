# Implementation Plan — Refactoring to Demo MVP Mode

This plan details the design and changes to refactor the project into a Demo MVP Mode, demonstrating a single Crop (Soybean), Region (Maharashtra), Date (Latest Available Date), and English Article with three translations.

## Proposed Changes

### [Component: Configuration & Database]

#### [MODIFY] [database.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/database.py)
- Add `query_latest_available_date(commodity: str) -> Optional[str]` to query the database and find the latest date for which records have been ingested for a given commodity.

---

### [Component: Scope Matrix & Analytics]

#### [MODIFY] [analytics.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/analytics.py)
- Simplify target scopes inside `build_scope_matrix` to exactly `{"soybean_maharashtra"}` under `DEMO_MODE`.
- In `compute_analytics`:
  - If `DEMO_MODE` is active and `commodity != "soybean"`, return an empty dictionary immediately.
  - If `DEMO_MODE` is active and `commodity == "soybean"`, filter incoming market data (`today_rows` and `prev_rows`) to only include records for state `"Maharashtra"`. This automatically simplifies all aggregations (average price, highest price, lowest price, arrival volume, and market count) to Maharashtra only.
  - Construct and return only the `"soybean_maharashtra"` payload. Skip all other scopes (national, Spotlight, Best Market, Top Gainers & Losers).

---

### [Component: English Article Generation & Caching]

#### [MODIFY] [seo_assembler.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/seo_assembler.py)
- In `write_article_file`, when `DEMO_MODE` is active and the scope is `"soybean_maharashtra"`, also write a copy of the JSON output as `article_soybean_maharashtra_latest_{lang}.json` under the cache directory `output/json/` to satisfy the custom cache naming requirement.

#### [MODIFY] [main.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py)
- In `_find_cached_output`, add `article_soybean_maharashtra_latest_{language}.json` (and variants) to candidates if `DEMO_MODE` is active and scope is `"soybean_maharashtra"`.
- In `main`:
  - If `mode == "demo"`, override the commodities list to run only `"soybean"`.
  - After Stage 1 (Ingest), query the database using `query_latest_available_date("soybean")` to find the latest available date. Override `args.date` (and downstream run variables) to this latest date for all subsequent stages (analytics, generation, translation, evaluation, and static site rendering).

---

## Verification Plan

### Automated Tests
- Run `pytest` to confirm all unit tests continue to pass. Update tests in `tests/test_pipeline_optimization.py` if needed.

### Manual Verification
- Clear the output directory:
  `Remove-Item -Recurse -Force output`
- Run the pipeline:
  `python main.py --mode demo`
- Verify that:
  - Exactly **1 English article** (`soybean_maharashtra`) is generated.
  - The article is translated into Hindi (`hi`), Marathi (`mr`), and Gujarati (`gu`) in a single translation API call.
  - Cache copy `article_soybean_maharashtra_latest_en.json` (and translations) is written in the output cache.
  - Total files published in the quality report equals **4**.
  - Pipeline duration is **< 60 seconds**, consuming exactly **2 Gemini API calls** (1 generation, 1 translation).
