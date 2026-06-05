# MandiBhav Dynamic Platform Architecture

```mermaid
flowchart LR
    OGD[OGD API] --> INGEST[Python ingestion]
    INGEST --> ANALYTICS[Analytics and scope builder]
    ANALYTICS --> GEN[Article generation and translation]
    GEN --> VALIDATE[Truthfulness, SEO, credibility checks]
    VALIDATE --> SUPABASE[(Supabase PostgreSQL)]
    SUPABASE --> WEB[Next.js App Router]
    WEB --> VERCEL[Vercel deployment]

    SUPABASE --> SEARCH[Supabase query search]
    SUPABASE --> SEO[Dynamic sitemap, robots, metadata, JSON-LD]
    SUPABASE --> FUTURE[Future AI surfaces: embeddings, RAG, recommendations]
```

## Runtime responsibilities

- Python remains the ingestion, analytics, validation, and article-authoring engine.
- Supabase becomes the source of truth for `market_data`, `articles`, and `pipeline_runs`.
- Next.js becomes the only publishing layer for public readers.
- Vercel hosts the Next.js app and serves dynamic SEO endpoints.

## Non-goals in the target state

- GitHub Pages is not the primary publishing layer.
- Static HTML generation is not required for routine publishing.
- SQLite is not the source of truth after cutover.
