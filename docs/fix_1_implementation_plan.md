# MandiBhav Pipeline Production-Readiness Audit Implementation Plan

This plan details the diagnosis and proposed fixes for the data ingestion and Gemini content generation issues in the MandiBhav by GramIQ pipeline.

## User Review Required

> [!IMPORTANT]
> **Key Architecture Preservation**: We are retaining the existing pipeline flow and database schema. All changes are backward-compatible.
> **Google GenAI SDK Structured Outputs**: We are using the native `response_schema` option of the `google-genai` Python client. This guarantees structured JSON responses conforming to Pydantic models directly from the API, eliminating any manual parsing and malformed JSON errors.
> **Demo Configuration**: By adding `PIPELINE_MODE=demo`, the pipeline defaults to Mock data, restricts generation to 4 scopes, and defaults to English-only (skipping translations).

## Open Questions
*No open questions are pending as the requirements are fully defined.*

## Proposed Changes

---

### [Component: Configuration & Paths]

We will extend `config.py` to support `DEBUG_OGD_SCHEMA`, `DEMO_MODE`, and the pipeline's runtime state `quota_exhausted_mode`.

#### [MODIFY] [config.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/config.py)
- Support `"demo"` in the allowed modes for `PIPELINE_MODE`.
- Define `DEMO_MODE` based on the environment variable or `PIPELINE_MODE == "demo"`.
- Define `DEBUG_OGD_SCHEMA` based on the environment variable (default: `False`).
- Define `quota_exhausted_mode` (boolean, default: `False`) to track quota exhaustion across modules.

---

### [Component: Ingestion Layer]

We will fix the mixed-case key bug in the API request, implement the schema discovery mode, and implement the fallback query strategy.

#### [MODIFY] [ingestion.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/ingestion.py)
- Correct the query parameter from `"filters[Arrival_Date]"` to the lowercase field ID `"filters[arrival_date]"`.
- Correct `"filters[commodity]"` to `"filters[commodity]"` (already lowercase).
- Implement `run_schema_discovery()` inside `LiveProvider` to fetch 5 records without filters, print the first record and list all field names, then automatically check and report if `Arrival_Date`, `commodity`, `Commodity`, or `arrival_date` are present in the returned record keys. Call this method during initialization if `config.DEBUG_OGD_SCHEMA` is active.
- Refactor `LiveProvider.fetch_market_data` to execute the fallback strategy:
  1. **Query 1**: `date` + `commodity` filters.
  2. **Query 2**: `commodity` filter only (no date filter).
  3. **Query 3**: Latest records (no filters, fetch 100 records and filter locally for the requested commodity's values).
  4. **Fallback to Mock**: If all queries fail or return 0 records, instantiate `MockProvider` and return mock data.
- Update `MockProvider._load_csv` and `LiveProvider._parse_ogd_records` to parse the actual date from the record when possible.
- Update `MockProvider` and `LiveProvider` logging to output `validation failure` for any record that fails Pydantic schema validation.

---

### [Component: Database Layer]

We will improve insert diagnostics to log specific details for duplicate keys, validation failures, and database constraint violations.

#### [MODIFY] [database.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/database.py)
- In `insert_market_records`, explicitly log:
  - `"Skipped record due to duplicate key: ..."` for duplicate keys.
  - `"Skipped record due to constraint violation: ..."` on `sqlite3.IntegrityError`.
  - `"Skipped record due to unexpected error/constraint violation: ..."` for other write exceptions.

---

### [Component: Analytics Layer]

We will restrict target scope generation when `DEMO_MODE` is enabled.

#### [MODIFY] [analytics.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/analytics.py)
- In `build_scope_matrix`, if `config.DEMO_MODE` is enabled, filter the scope target list to only allow:
  1. `soybean_national`
  2. `soybean_maharashtra`
  3. `cotton_national`
  4. `cotton_gujarat`
  (Max 4 articles).

---

### [Component: LLM & Translation Engines]

We will enforce structured output via native Pydantic schemas, fix retry delay parsing, and implement quota exhaustion short-circuiting.

#### [MODIFY] [llm_engine.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/llm_engine.py)
- Define Pydantic schemas for LLM batching:
  ```python
  class ScopeArticleDraft(BaseModel):
      scope_key: str
      title: str
      body_html: str

  class BatchArticleResponse(BaseModel):
      articles: list[ScopeArticleDraft]
  ```
- Configure `response_schema=BatchArticleResponse` in `GenerateContentConfig` for Gemini calls.
- Read response from `response.parsed`.
- Implement `extract_retry_delay(e: Exception) -> float` to parse the delay seconds directly from the `e.details` dict or the exception message for a 429 rate limit. Cap the sleep time to `60.0` seconds.
- Catch 429 and 503 separately:
  - **429 (Resource Exhausted)**: Set `config.quota_exhausted_mode = True`, log the failure, and return immediately without sleeping or retrying.
  - **503 (Unavailable)**: Log retry warning and sleep before retrying.
- Short-circuit `generate_articles_for_commodity` if `config.quota_exhausted_mode` is active.

#### [MODIFY] [translator.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/translator.py)
- Define Pydantic schemas for translation batching:
  ```python
  class SingleTranslation(BaseModel):
      scope_key: str
      language_code: str
      title: str
      meta_description: str
      body_html: str

  class BatchTranslationResponse(BaseModel):
      translations: list[SingleTranslation]
  ```
- Configure `response_schema=BatchTranslationResponse` in `GenerateContentConfig` for translation calls.
- Read response from `response.parsed`.
- Handle 429 (quota exhaustion) and 503 (service unavailable) separately. Short-circuit translation if `config.quota_exhausted_mode` is active.

---

### [Component: Orchestrator & Static Site Assembly]

We will implement the cache lookup checks, write generated files to the global cache folder, and configure demo mode variables.

#### [MODIFY] [main.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py)
- In `parse_args`, add `"demo"` to choices for `--mode`.
- Add global json cache path candidate `config.OUTPUT_DIR / "json" / f"article_{scope_key}_{language}.json"` in `_find_cached_output`.
- Skip translation by default if `mode == "demo"`, unless overridden.
- In `stage_generate_and_assemble`, check `config.quota_exhausted_mode` and break/skip if active.

#### [MODIFY] [seo_assembler.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/seo_assembler.py)
- In `write_article_file`, write a copy of the final article JSON to `output_dir / "json" / f"article_{scope_key}_{language}.json"` to serve as a cache file for future runs.

---

## Verification Plan

### Automated Tests
- Run `pytest` to verify all unit tests pass.
- Write new unit tests in `tests/test_pipeline_optimization.py` verifying:
  - Cache lookup works correctly.
  - Fallback queries occur in sequence.
  - Pydantic structured output validation is correctly integrated.
  - `retryDelay` is successfully parsed.

### Manual Verification
- Execute `python main.py --mode demo --date 2026-06-05` to verify a full run works without exceptions in demo mode.
- Execute `python build_site.py --date 2026-06-05` to build the static site and verify the output.
