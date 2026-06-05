# Implementation Plan — MandiBhav Data Integrity & Truthfulness Refactoring

This plan details the design and implementation steps to transform the MandiBhav by GramIQ pipeline into a factually honest, data-grounded, and transparent market intelligence report. Every claim in the generated articles will be fully traceable to actual analytics, and the report will never exceed the confidence justified by the underlying data.

## Root Cause Analysis

1. **Misleading Live Indicator**: The pipeline used cached articles or mock fallback data when the live OGD API failed or was bypassed, but the generated articles still presented themselves as "live" daily updates.
2. **Inflated Confidence Scoring**: The confidence score was calculated using a completeness heuristic that rewarded market density but failed to penalize mock fallbacks or cache hits, routinely returning `1.0` even for mock fallback data.
3. **Template Contradictions**: The local fallback templates included static, creative descriptions (e.g., "substantial influx of supply", "bagging and weighing operations") which directly contradicted the data when arrivals were `0.0` tonnes.
4. **Unsupported Claims**: Generated text frequently referenced market forces like "crusher demand", "oil mill demand", "local processors", and "market liquidity" that do not exist anywhere in the raw OGD datasets.
5. **Scope Violations**: Articles written for narrow scopes (like `soybean_nagpur`) used statewide context ("across Maharashtra") to sound more authoritative, violating geographic consistency.
6. **Lack of Report Modes**: Single-record data points were treated with the same analytical depth, outlooks, and predictions as large-scale national datasets.
7. **No Truthfulness Gate**: The quality evaluator only measured formatting and structural criteria, completely ignoring factual correctness and data contradictions.

---

## Proposed Changes

### [Component: Data Schemas]

#### [MODIFY] [schemas.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/schemas.py)
- In `AnalyticsPayload`, add `record_count: int = 0` to track the raw OGD records analyzed.
- In `ArticleDraft`, add `observed_facts: list[str]`, `safe_inferences: list[str]`, and `blocked_claims: list[str]` to support the two-stage generation process.
- In `FinalArticleJSON`, replace or supplement `confidence_score` with the following new fields:
  - `data_source_status: str` (`LIVE` | `CACHE` | `MOCK` | `LIVE_PLUS_CACHE`)
  - `credibility_score: float` (0.0 to 1.0)
  - `report_type: str` (`FULL_REPORT` | `LIMITED_DATA_REPORT`)
  - `contradictions_count: int`
  - `unsupported_claims_count: int`
  - `scope_violations_count: int`
  - `truthfulness_score: float`

---

### [Component: Ingestion & Source Tracking]

#### [MODIFY] [ingestion.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/ingestion.py)
- Inside the `LiveProvider.fetch_market_data` method, if the OGD API query fails or is empty and it falls back to `MockProvider`, set `config.ingestion_data_source = "MOCK"`.
- If the OGD API query is successful, set `config.ingestion_data_source = "LIVE"`.
- In `MockProvider.fetch_market_data`, set `config.ingestion_data_source = "MOCK"`.
- Record the count of raw records successfully parsed and set `config.demo_records_count = len(records)`.

---

### [Component: Analytics & Payload Enrichment]

#### [MODIFY] [analytics.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/analytics.py)
- Capture `config.demo_records_count` (or the size of the ingested dataset) and inject it into the `AnalyticsPayload.record_count` field.

---

### [Component: Two-Stage Content Generation]

#### [MODIFY] [llm_engine.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/llm_engine.py)
- Refactor the Gemini API JSON output schema (`BatchArticleResponse`) to return the structured `ScopeArticleStage1Draft` Pydantic model:
  - **Stage 1**: Generates `observed_facts`, `safe_inferences`, and `blocked_claims`.
  - **Stage 2**: Generates `body_html` using ONLY the observed facts and safe inferences.
- Update the fallbacks (`_generate_nagpur_demo_fallback`, etc.) to:
  - Return `ArticleDraft` with populated facts, inferences, and blocked lists.
  - Apply strict post-processing regex corrections to strip out disallowed words (e.g., "crusher", "oil mill", "processor", "liquidity") and ensure arrivals=0 text is completely factual and free of contradictions.

---

### [Component: Translation & Fallbacks]

#### [MODIFY] [translator.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/translator.py)
- Apply regex cleaning to Hindi, Marathi, and Gujarati local translation fallbacks:
  - Replace translated terms for "crusher", "oil mill", and "liquidity" with safe alternatives.
  - Automatically correct "busy platforms" and "bagging/weighing" in translations if the modal price/arrivals are 0.

---

### [Component: Truthfulness Validation & Credibility Scoring]

#### [MODIFY] [seo_assembler.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/seo_assembler.py)
- Implement `validate_article_against_analytics(body_html, analytics)`:
  - If arrivals is 0, forbid: `"heavy arrivals"`, `"strong supply"`, `"substantial influx"`, `"busy market"`, `"influx of supply"`, `"active trade activity"`, `"bagging and weighing"`.
  - If `record_count < 5`, forbid: `"trend"`, `"regional demand"`, `"market momentum"`, `"future outlook"`, `"market trends"`.
- Implement `validate_allowed_facts_only(body_html)`:
  - Forbid: `"crusher"`, `"oil mill"`, `"processor"`, `"liquidity"`, `"macroeconomic"`, `"shipping logistics"`.
- Implement `validate_scope_consistency(body_html, scope)`:
  - If Nagpur scope, forbid Maharashtra-wide or national generalizations.
- Implement the new **Credibility Scoring System**:
  - `LIVE` base score = `0.80 + 0.15 * min(record_count / 15.0, 1.0)`.
  - `LIVE_PLUS_CACHE` base score = `0.80 + 0.15 * min(record_count / 15.0, 1.0)`.
  - `MOCK` base score = `0.60 + 0.10 * min(record_count / 15.0, 1.0)`.
  - `CACHE` base score = `0.55` (if generated from mock data) or `0.85` (if generated from live data).
  - Penalties: `* 0.9` if fallback generation was used, `* 0.8` if translation failed/skipped.
  - Set score to `0.0` if contradictions are found.
  - Cap score at `0.70` if mock data is used.
- Add **Data Source Disclosures** in `assemble_final_article`:
  - **Header**: Inject prominent HTML block summarizing data source status (`Live OGD Data`, `Cached Data`, or `Mock Demo Data`).
  - **Footer**: Inject detailed disclosure containing Source, Market, Records Analyzed, Data Source, and Report Type.
  - Localize the header and footer in English, Hindi, and Marathi.
- Implement the **Publishing Gate** (Problem 10):
  - Auto-publish is allowed ONLY if `truthfulness_score >= 0.80` and `contradictions_count == 0`.
  - Otherwise, status is forced to `review_required`.

---

### [Component: Quality Report & Evaluator]

#### [MODIFY] [evaluate.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/evaluate.py)
- Update `ArticleMetrics` and `EvaluationReport` to aggregate:
  - Contradictions count
  - Unsupported claims count
  - Scope violations count
  - Fallback disclosure presence
  - Data source disclosure presence
  - Average truthfulness score
- Print the `TRUTHFULNESS & TRANSPARENCY` block in the quality report:
  ```text
  TRUTHFULNESS & TRANSPARENCY
  ├── Contradictions:           0  ✅
  ├── Unsupported claims:       0  ✅
  ├── Scope violations:         0  ✅
  ├── Fallback disclosure:      100.0%  ✅
  ├── Data source disclosure:   100.0%  ✅
  └── Avg truthfulness score:   1.000  ✅
  ```

---

### [Component: Orchestrator]

#### [MODIFY] [main.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py)
- Resolve `data_source_status` at runtime:
  - Cache hit: `LIVE_PLUS_CACHE` (if live OGD succeeded) or `CACHE` (if live OGD failed/skipped).
  - Cache miss: `LIVE` (if live OGD succeeded) or `MOCK` (if live OGD failed/skipped).
- Print the data source status in the final summary block:
  ```text
  Publishing:
  GitHub Pages SKIPPED (Data Source: LIVE)
  ```

---

## Verification Plan

### Automated Tests
- Run `pytest` to verify all 36 unit tests continue to pass.
- Add a new unit test suite `tests/test_truthfulness.py` to assert credibility scores, contradiction detection, scope consistency, and header/footer disclosure generation.

### Manual Verification
1. Run `python clear_date.py --date 2026-06-05` to clear cache.
2. Run `python main.py --mode demo --date 2026-06-05 --skip-publish` using live OGD data. Verify:
   - Evaluator output includes the new truthfulness checks.
   - Header disclosure `Data Source: Live OGD Data` is injected.
   - Footer transparency disclosure is injected.
   - Word count and other KPIs remain 100% compliant.
3. Simulate OGD failure (offline mode) to verify that `MOCK` data source status is assigned, the credibility score is capped at `0.70`, and header displays `Mock Demo Data`.
4. Intentionally inject contradiction text into a mock output file and run `python main.py --evaluate-only` to verify the gate flags it and prevents publication.
