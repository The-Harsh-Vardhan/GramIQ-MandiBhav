# MandiBhav by GramIQ

Automated mandi-price content pipeline for soybean and cotton using:
- OGD mandi data or local CSV fixtures
- Python analytics
- Gemini English article generation
- Gemini batched translations
- Supabase-backed article persistence
- Next.js publishing on Vercel

## Target Architecture

```text
OGD API
-> Python ingestion and analytics
-> Supabase PostgreSQL
-> Next.js App Router
-> Vercel
```

SQLite and static-site generation remain available only as compatibility paths. The intended
end state is `DATA_BACKEND=supabase` and `PUBLISHING_TARGET=vercel`.

## Quick Start

Detailed setup lives in [docs/quickstart.md](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/docs/quickstart.md>).

Minimal setup:

```bash
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
PIPELINE_MODE=live
OGD_API_KEY=your_ogd_api_key
OGD_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
OGD_PAGE_LIMIT=1000
DATA_BACKEND=supabase
PUBLISHING_TARGET=vercel
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_public_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
WRITE_ARTICLE_ARTIFACTS=false
```

Then run:

```bash
python main.py --date 2026-06-04 --mode live
```

If you want a no-network sanity check first:

```bash
python main.py --mode dev
```

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Gemini generation and translation |
| `PIPELINE_MODE` | No | `dev` or `live`; defaults to `dev` |
| `OGD_API_KEY` | Live only | data.gov.in API key |
| `OGD_RESOURCE_ID` | No | Defaults to the OGD mandi dataset resource |
| `OGD_PAGE_LIMIT` | No | Per-request OGD page size; defaults to `1000` |
| `GEMINI_MODEL` | No | Override Gemini model if needed |
| `DATA_BACKEND` | Recommended | `supabase` for the target architecture |
| `PUBLISHING_TARGET` | Recommended | `vercel` to disable GitHub Pages publishing |
| `SUPABASE_URL` | Supabase only | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase frontend | Public browser key for the Next.js app |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase pipeline | Server-side key for Python upserts |
| `WRITE_ARTICLE_ARTIFACTS` | No | `false` for database-first runs |

## Live OGD Ingestion

The live provider calls:

```text
GET /resource/9ef84268-d588-465a-a308-a864a43d0070
```

with query parameters:

```text
api-key=<OGD_API_KEY>
format=json
offset=<page offset>
limit=<OGD_PAGE_LIMIT>
filters[Arrival_Date]=DD/MM/YYYY
filters[commodity]=Soyabean|Soybean|Cotton
```

Notes:
- OGD arrivals are parsed from quintals and converted to tonnes.
- The code paginates until a page returns fewer than `OGD_PAGE_LIMIT` rows.
- For soybean, the live provider tries `Soyabean` first, then `Soybean`.
- If live mode fails, the pipeline falls back to `data/mock/` and logs that fallback.

## How To Verify Live Mode

Run:

```bash
python main.py --mode live --date 2026-06-04 --skip-translate
```

Look for logs like:
- `Using LiveProvider (OGD API)`
- `OGD API returned ...`
- `Using OGD commodity filter 'Soyabean' ...`

If you instead see:
- `falling back to MockProvider`

then the OGD key, connectivity, or dataset response needs attention.

## Data Ingestion Flow

```text
CLI
-> get_provider()
-> LiveProvider or MockProvider
-> fetch current-day records
-> store in Supabase or SQLite
-> fetch previous-day records
-> store in Supabase or SQLite
-> analytics
```

## Current Content Pipeline

```text
Data
-> Analytics
-> Gemini batch English generation per commodity
-> Deterministic Python SEO/FAQs/tables
-> Gemini batch translation per commodity
-> Article repository upsert
-> Next.js frontend reads from Supabase
```

## Common Commands

```bash
python main.py
python main.py --mode live
python main.py --mode live --commodities soybean
python main.py --skip-translate
python main.py --evaluate-only --date 2026-06-04
pytest
```

Frontend setup and deployment are in [docs/supabase-vercel-migration.md](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/docs/supabase-vercel-migration.md>).

## Project Files To Know

| File | Role |
|---|---|
| [config.py](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/config.py>) | env vars, paths, OGD constants |
| [ingestion.py](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/ingestion.py>) | mock/live providers and ingestion flow |
| [analytics.py](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/analytics.py>) | Python-only analytics |
| [main.py](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/main.py>) | pipeline orchestration |
| [repository.py](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/repository.py>) | canonical article persistence abstraction |
| [supabase_backend.py](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/supabase_backend.py>) | Supabase REST storage adapter |
| [web/package.json](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/web/package.json>) | Next.js frontend for Vercel |
| [docs/quickstart.md](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/docs/quickstart.md>) | setup and troubleshooting |
| [.env.example](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/.env.example>) | starter env template |

## Tests

```bash
pytest
pytest tests/test_ingestion.py -v
pytest tests/test_analytics.py -v
```

The ingestion tests now cover:
- mock CSV loading
- schema validation
- OGD record parsing
- commodity alias selection in live mode
