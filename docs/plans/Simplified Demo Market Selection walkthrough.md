# Walkthrough - Simplified Demo Market Selection

We simplified the `select_demo_market` logic in `mandibhav/discovery.py` to prevent hangs in the demo pipeline. All historical date lookups, looping, and 7-day or 30-day window querying have been removed.

## Changes Made

### 1. Market Discovery Layer (`mandibhav/discovery.py`)
- Modified [fetch_ogd_raw_records](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/mandibhav/discovery.py#L60) to accept a custom `timeout: Optional[tuple[float, float]] = None` parameter. When a custom timeout is specified, `max_attempts` is restricted to `1` (bypassing retries and backoffs) to fail fast.
- Rewrote [select_demo_market](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/mandibhav/discovery.py#L486) to run under 2 seconds:
  1. Fetches today's Soyabean records from OGD with `timeout=(1.0, 1.0)`.
  2. If they exist, grabs the first record and uses its market/state.
  3. If they don't, queries today's OGD records without filter (using `timeout=(1.0, 1.0)`) and uses the first record found.
  4. If no records exist today at all, directly falls back to `MockProvider` and uses its first record.
  5. Implemented precise logs for Soybean records found today:
     ```
     Found {count} Soyabean records today.
     Selected:
     Market: {market}
     State: {state}
     ```

### 2. Ingestion Layer (`ingestion.py`)
- Adjusted [ingest_commodity](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/ingestion.py#L678): on a database cache hit in demo mode, `config.demo_chosen_market` and `config.demo_chosen_state` are dynamically aligned with the cached records to prevent "No market data" errors during analytics.

### 3. Pipeline Core CLI (`main.py`)
- Initialized `pipeline_duration = 0.0` at the top of the date loop in [main.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/main.py#L630) to prevent an `UnboundLocalError` when the pipeline skips stages due to empty scope targets.

---

## Verification Results

### Automated Tests
- Ran `pytest` successfully. All 67 tests in the test suite passed, verifying that the new logic remains fully backward-compatible with mock environments.

### Manual Verification
- Ran `python main.py --mode demo`:
  - Verified it correctly catches connection/read timeouts within 1 second.
  - Successfully logged the fallback market selection and loaded data from cache.
  - Completed the entire pipeline without hanging or throwing errors.
