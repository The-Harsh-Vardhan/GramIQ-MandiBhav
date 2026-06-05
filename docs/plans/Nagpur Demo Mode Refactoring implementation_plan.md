# Implementation Plan — Nagpur Demo Mode Refactoring

This plan details the design and changes to refactor the project into a robust, high-performance **Nagpur Demo Mode** that runs in under 60 seconds with live OGD data, guarantees data fallback, aggregates duplicate logging, implements cache isolation, and outputs clean logs.

## User Review Required

> [!IMPORTANT]
> The refactor modifies the default behavior under `PIPELINE_MODE=demo` to target the `soybean_nagpur` scope (Nagpur Soybean, Maharashtra) instead of `soybean_maharashtra` (entire state).
>
> We will introduce a local translation and generation fallback for the `nagpur_demo` article type. This ensures that the demo *never* fails due to Gemini rate limits or API quota issues.

## Proposed Changes

---

### [Component: Configuration & Paths]

#### [MODIFY] [config.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/config.py)
- Change default `PIPELINE_MODE` to `demo` (or support loading it).
- Under `DEMO_MODE`, set targeted languages to Hindi (`hi`) and Marathi (`mr`) only (omit Gujarati `gu` for the demo).
- Define cache namespaces/subdirectories in the output directory:
  - Demo Cache: `output/json/demo/`
  - Production Cache: `output/json/production/`

---

### [Component: Data Ingestion & Date Normalization]

#### [MODIFY] [ingestion.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/ingestion.py)
- In `LiveProvider._call_ogd_api_page`, support optional `state_filter` and `market_filter` query parameters.
- In `LiveProvider.fetch_market_data`:
  - When in `demo` mode, set `state_filter = "Maharashtra"` and `commodity_filter = "Soyabean"`.
  - Try to fetch Nagpur APMC records from the OGD API first.
  - If no records are returned (or if market filtering isn't supported), fetch all Maharashtra Soybean records for the target date.
  - Implement a local fallback filter: **Nagpur APMC** → **Amravati** → **Wardha** → **Any Maharashtra Soybean Market**.
  - Keep only the records for the first matching market from that hierarchy, ensuring the demo always targets exactly one market.
- Optimize pagination: In `_fetch_all_pages`, stop fetching if total records found > 20 or page > 3.
- In `_parse_ogd_records`, parse the raw OGD arrival date exactly (without timezone conversion or current date replacement). Add a debug log matching the exact format:
  `Raw OGD Date: <raw> | Parsed Date: <parsed> | Stored Date: <stored>`

---

### [Component: Database Duplicate Aggregation]

#### [MODIFY] [database.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/database.py)
- Refactor `insert_market_records` to aggregate skipped duplicate keys into a counter `duplicates_skipped`.
- Suppress the individual log lines (`Skipped record due to duplicate key...`).
- Print a single database insertion summary:
  ```text
  Database:
  Inserted: X
  Duplicates: Y
  ```

---

### [Component: Analytics & Scope Matrix]

#### [MODIFY] [analytics.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/analytics.py)
- In `compute_analytics` under `DEMO_MODE`:
  - Restrict the target commodity to `soybean`.
  - Build metrics and payloads exclusively for the selected fallback/target market (e.g. Nagpur).
  - Set `scope_key = "soybean_nagpur"`, `article_type = "nagpur_demo"`, `scope_label = chosen_market_name` (e.g., "Nagpur"), and `market = chosen_market_name`.
- In `build_scope_matrix` under `DEMO_MODE`, filter output scope targets to exclusively allow `"soybean_nagpur"`.

---

### [Component: Article Generation & Local Fallbacks]

#### [MODIFY] [templates/prompts/article_types.json](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/templates/prompts/article_types.json)
- Add a new article type entry `"nagpur_demo"` containing instructions to generate a structured 400-700 word article covering the required headers:
  1. Executive Summary
  2. Market Snapshot
  3. Price Analysis
  4. Market Highlights
  5. MSP Comparison
  6. Farmer Advice
  7. AI Outlook

#### [MODIFY] [llm_engine.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/llm_engine.py)
- Define a high-quality local fallback draft generator for the `"nagpur_demo"` article type to serve as a zero-Gemini-cost fallback.
- In `generate_articles_for_commodity`, if Gemini generation fails, is rate-limited, or returns an invalid draft under 300 words, fall back to this local generator.

---

### [Component: Translation & Local Fallbacks]

#### [MODIFY] [translator.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/translator.py)
- Define high-quality, pre-translated local fallbacks for the `"nagpur_demo"` article structure in Hindi and Marathi.
- In `translate_articles`, if Gemini translation fails, falls back to these pre-rendered templates to guarantee execution completes successfully.

---

### [Component: SEO Metadata & Cache Isolation]

#### [MODIFY] [seo_assembler.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/seo_assembler.py)
- Modify `generate_seo_metadata` to automatically construct SEO titles like `"Soybean Price Today in Nagpur Mandi"` (or relevant fallback market name) deterministically without calling Gemini.
- Include `"seo_title"` in the final article output dictionary to satisfy schema requirements.
- In `write_article_file`, write cache outputs under isolated directories:
  - Demo cache: `output/json/demo/soybean_nagpur_latest_{lang}.json`
  - Production cache: `output/json/production/article_{scope}_{lang}.json`

---

### [Component: Orchestrator & Logging]

#### [MODIFY] [main.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py)
- Refactor `_find_cached_output` to check the isolated cache namespaces:
  - In demo mode, load from `output/json/demo/soybean_nagpur_latest_{lang}.json`
  - In production mode, load from `output/json/production/article_{scope}_{lang}.json`
- In `main`:
  - When in `demo` mode, override targets to `commodity="soybean"` and run for the latest available date for the chosen market.
  - Collect and store stats throughout all pipeline phases.
  - At the very end of the script, output a clean, formatted block:
    ```text
    OGD Fetch:
    Commodity: Soybean
    Market: Nagpur (or chosen fallback)
    Records: X

    Database:
    Inserted: X
    Duplicates: Y

    Analytics:
    Average Price: ₹XXXX

    Generation:
    Article Generated (or Cache Hit)

    Translation:
    Hindi ✓
    Marathi ✓

    Publishing:
    GitHub Pages ✓
    ```

---

## Verification Plan

### Automated Tests
- Run `pytest` to confirm that existing unit tests pass.

### Manual Verification
1. Run cleanup script to purge existing databases/cache:
   `python clear_date.py --date 2026-06-05`
2. Run the pipeline in demo mode:
   `python main.py --mode demo --date 2026-06-05`
3. Verify:
   - Output log prints exactly the clean summary.
   - Execution time is `< 60` seconds.
   - Cache file is correctly created at `output/json/demo/soybean_nagpur_latest_en.json`.
   - The generated article contains exactly the required headings and is over 300 words.
   - Static pages are rendered in `site/` for English, Hindi, and Marathi.
