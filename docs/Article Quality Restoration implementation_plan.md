# Implementation Plan — MandiBhav Article Quality Restoration

This plan details the design and changes to restore daily article content quality to premium standards while keeping all previous infrastructure enhancements (caching, translation batching, rate-limit retries, and OGD API fallbacks).

## User Review Required

> [!IMPORTANT]
> **Automatic CTA Insertion**: We will automatically append the GramIQ CTA HTML footer in Python during article assembly. This guarantees 100% compliance without wasting LLM token budget or risking formatting issues.
> **Deterministic SEO Metadata**: SEO Titles (50-70 chars), Meta Descriptions (120-160 chars), and Keywords will be generated deterministically in Python using structured analytics, ensuring 100% compliance with length and keyword guidelines.
> **Demo Scope Expansion**: In `demo` mode, we will generate exactly 4 target articles (`soybean_national`, `soybean_maharashtra`, `cotton_national`, `cotton_gujarat`) instead of only 1. The default pipeline mode will be switched to `"demo"`.

---

## 1. Root Cause Analysis

The degradation in article quality (50–80 words, generic summaries) stems from:
1. **Prompt Word-Count Limits**: In `llm_engine.py`, the `_build_batch_prompt` instructed Gemini to write articles of `220-450` words.
2. **Missing Specific Prompts**: The CLI pipeline was not formatting/injecting the detailed prompts defined in `article_types.json` to guide the model's writing structure.
3. **Weak Quality Gates**: The validator did not enforce the 300-word minimum, CTA presence, or FAQ count, allowing low-quality drafts to pass.
4. **Artificial Confidence Score**: The confidence heuristic was too lenient and did not reflect validation failures.

---

## 2. Refactoring Plan & Proposed Changes

### [Component: Configuration & Defaults]

#### [MODIFY] [config.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/config.py)
- Change default `PIPELINE_MODE` to `"demo"`.
- Update `MIN_WORD_COUNT = 300` to enforce the new hard minimum.

#### [MODIFY] [.env](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/.env) & [.env.example](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/.env.example)
- Update default `PIPELINE_MODE=demo`.

---

### [Component: Ingestion & Analytics]

#### [MODIFY] [analytics.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/analytics.py)
- Update `build_scope_matrix` to filter target scopes under `DEMO_MODE` to exactly these 4:
  - `soybean_national`
  - `soybean_maharashtra`
  - `cotton_national`
  - `cotton_gujarat`
  (Max 4 articles).

---

### [Component: Prompt Templates]

#### [MODIFY] [templates/prompts/system_prompt.txt](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/templates/prompts/system_prompt.txt)
- Update instructions to require detailed agricultural journalism, a target length of 400 to 700 words, and the inclusion of all required narrative sections (Executive Summary, Market Snapshot, HTML Market Table, National Comparison, MSP Analysis, Seasonal Context, Farmer Actionable Advice, and AI Market Outlook).

#### [MODIFY] [templates/prompts/article_types.json](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/templates/prompts/article_types.json)
- Redefine structures for `daily_commodity_report` and `state_market_report` to specify the exact sections, detailed paragraphs, and table format required, setting the word targets to `500-700` and `450-650` respectively.

#### [MODIFY] [llm_engine.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/llm_engine.py)
- Modify `_build_batch_prompt` to load templates from `article_types.json`, format them with context details (commodity, state, averages, arrivals, MSP, and seasonal factors), and inject them as writing instructions for each target scope.

---

### [Component: SEO, Validation & Confidence Heuristics]

#### [MODIFY] [seo_assembler.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/seo_assembler.py)
- Implement `generate_seo_metadata(analytics, scope)`:
  - **SEO Title**: 50–70 characters containing Commodity, Region, and intent keyword.
  - **Meta Description**: 120–160 characters containing average modal price, arrivals, and region.
  - **Keywords**: Deterministic list containing all 6 required words.
- Implement `validate_article_quality(article)` checking:
  - Word count >= 300.
  - FAQ count >= 3.
  - GramIQ CTA block present.
- Update `assemble_article_output()` to:
  - Override Title, Meta Description, and Keywords with the deterministic SEO metadata.
  - Automatically append the HTML CTA footer to the end of the `body_html`.
- Update `compute_confidence()` to use:
  `confidence = data_completeness_score * generation_success_score * translation_success_score`
  - If `validate_article_quality` fails, set confidence to `0.0` and status to `"blocked"`.

---

## 3. Verification Plan

### Automated Tests
- Run `pytest` to verify that all existing tests pass.

### Manual Quality Checks
- Execute the pipeline in demo mode:
  `python main.py --mode demo --date 2026-06-05`
- Verify the quality report outputs:
  - Average word count > 400.
  - Published articles = 4.
  - CTA present = 100%.
  - SEO Title lengths are between 50 and 70 characters.
  - Meta Description lengths are between 120 and 160 characters.
  - Keyword and JSON-LD validations are all green (100%).
