# Supabase + Vercel Migration Guide

## What changed

- `DATA_BACKEND=supabase` switches market data and pipeline run storage from SQLite to Supabase.
- `PUBLISHING_TARGET=vercel` disables the legacy GitHub Pages publish step.
- The Python pipeline still generates and validates article content, but canonical article persistence now happens through `repository.py` into Supabase.
- The public site now lives in `web/` as a Next.js App Router project that queries Supabase directly.

## Supabase setup

1. Create a new Supabase project.
2. Apply the SQL schema in [202606060001_initial_schema.sql](</c:/D Drive/Projects/Summers 2026/GramIQ MandiBhav/supabase/migrations/202606060001_initial_schema.sql>).
3. Set these root `.env` values:

```dotenv
DATA_BACKEND=supabase
PUBLISHING_TARGET=vercel
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
PUBLIC_SITE_URL=https://mandibhav.gramiq.com
```

4. If `supabase` CLI is available, the schema can be pushed with:

```bash
supabase db push
```

## Pipeline behavior

- `main.py` keeps the ingestion, analytics, translation, evaluation, and truthfulness flow.
- `database.py` routes `market_data` and `pipeline_runs` calls to Supabase when `DATA_BACKEND=supabase`.
- `write_article_file()` still writes JSON artifacts to `output/` for evaluation and cache compatibility, but the source of truth for publishing becomes Supabase.
- Historical runs with `--backfill-days`, `--start-date`, and `--end-date` automatically populate the same `articles` table that the Next.js frontend reads.

## Vercel setup

The Vercel CLI is authenticated in this environment as `the-harsh-vardhan`.

1. Install frontend dependencies inside `web/` using the repo's containerized package-install policy.
2. Link the frontend directory explicitly:

```bash
npx vercel link --yes --cwd web --project mandibhav --scope <team-or-user>
```

3. Add production environment variables:

```bash
npx vercel env add NEXT_PUBLIC_SUPABASE_URL production
npx vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production
npx vercel env add SITE_URL production
```

4. Add preview variables too if preview deployments should work against a separate Supabase project.
5. Deploy from the frontend directory:

```bash
npx vercel --cwd web
npx vercel --cwd web --prod
```

## Next.js surface

- `/` shows latest reports, featured report, search input, and commodity filter.
- `/archive` supports pagination plus commodity, market, keyword, and date filtering through Supabase queries.
- `/article/[slug]` renders the canonical article body with transparency metadata.
- `/about` explains the methodology and architecture.
- `sitemap.ts` and `robots.ts` generate SEO endpoints dynamically from stored content.
