# Quickstart

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Create `.env`

```bash
copy .env.example .env
```

Recommended live-mode starter:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
PIPELINE_MODE=live
OGD_API_KEY=your_ogd_api_key
OGD_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
OGD_PAGE_LIMIT=1000
```

If you just want to smoke-test the pipeline without OGD:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
PIPELINE_MODE=dev
```

## 3. OGD API Key

The OGD mandi endpoint in this repo defaults to:

```text
https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
```

The public docs also show a test key:

```text
579b464db66ec23bdd000001a19088a22a72469b46974157ac49b624
```

Use that only for initial validation. For regular usage, put your own OGD key in `.env`.

## 4. Run The Pipeline

Dev mode:

```bash
python main.py --mode dev
```

Live mode:

```bash
python main.py --mode live --date 2026-06-04
```

Live mode, faster smoke test:

```bash
python main.py --mode live --date 2026-06-04 --skip-translate --commodities soybean
```

## 5. Verify Ingestion

Successful live ingestion should log:
- `Using LiveProvider (OGD API)`
- `OGD API returned ...`
- `Using OGD commodity filter '...'`

If live ingestion fails, the repo intentionally falls back to mock CSV fixtures. You will see:
- `LiveProvider unavailable ... falling back to MockProvider`
- or `Falling back to MockProvider ...`

That means content generation still runs, but you are not using real OGD data.

## 6. Build The Static Site

```bash
python build_site.py --date 2026-06-04
```

## 7. Run Tests

```bash
pytest
```

## OGD Request Shape Used By The Repo

The live provider calls OGD with:

```text
api-key=<OGD_API_KEY>
format=json
offset=<offset>
limit=<OGD_PAGE_LIMIT>
filters[Arrival_Date]=DD/MM/YYYY
filters[commodity]=<commodity alias>
```

For soybean the code tries:
1. `Soyabean`
2. `Soybean`

For cotton the code tries:
1. `Cotton`

## Troubleshooting

`403 Forbidden`
- usually means the OGD key is invalid, expired, or rate-limited

`No records fetched`
- the date may have no published rows yet
- the commodity label may differ in the upstream dataset
- live mode may have fallen back to mock mode

`Gemini initialization failed`
- `GEMINI_API_KEY` is missing or invalid

`Pipeline runs but uses fixtures`
- check `PIPELINE_MODE=live`
- check `OGD_API_KEY`
- rerun with `--verbose`
