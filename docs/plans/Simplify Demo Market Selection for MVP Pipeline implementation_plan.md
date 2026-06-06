# Simplify Demo Market Selection for MVP Pipeline

The demo pipeline is currently hanging because `select_demo_market` performs extensive backward historical date search and queries OGD API in a loop when live data is missing or incomplete for the current date. For the MVP, this complex logic is being replaced with a fast, direct approach.

## Proposed Changes

### Discovery Layer

#### [MODIFY] [discovery.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/mandibhav/discovery.py)
- Rewrite `select_demo_market` to:
  1. Fetch today's Soyabean records from OGD (or mock records if `PIPELINE_MODE` is `dev`).
  2. If records exist:
     - Select the first record.
     - Extract and return its market and state.
  3. If no Soybean records exist:
     - Fetch today's records without commodity filter.
     - Select the first record that has both market and state defined, and use its market and state.
  4. If no records exist at all today:
     - Fall back to MockProvider (via `fetch_mock_raw_records("soybean")`), select the first record, and use its market and state.
  5. Log the results in the exact requested format:
     ```
     Found {count} Soyabean records today.
     Selected:
     Market: {market}
     State: {state}
     ```
  6. Remove the historical day-by-day lookup (`find_latest_available_data`) from the demo market selection flow.

## Verification Plan

### Automated Tests
- Run `pytest tests/test_discovery.py` to ensure all discovery tests continue to pass (using dev/mock data).
- Run all tests: `pytest`

### Manual Verification
- Execute `python main.py --mode demo` to verify that the selection runs quickly (under 2 seconds) and logs the selected market and state appropriately.
