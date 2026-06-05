# Future RAG Extension Plan

This repository now prepares for AI extensions without implementing them in the live path.

## Prepared foundations

- `articles.ai_metadata` is reserved for embedding metadata, chunk manifests, and model provenance.
- Canonical article bodies live in Supabase, which is a stable source for chunking and retrieval.
- `market_data` is normalized, which supports retrieval over raw records or derived analytics later.
- `pipeline_runs` records can anchor observability for future embedding or recommendation jobs.

## Recommended phase order

1. Add a chunking job that materializes article sections into a new `article_chunks` table.
2. Add `pgvector` and a nullable embedding column only when the embedding model choice is fixed.
3. Backfill embeddings from published articles only after chunking and provenance fields are finalized.
4. Introduce a retrieval API for the Next.js app or a separate chatbot surface.
5. Add recommendation features from nearest-neighbor matches and commodity or market similarity.

## Suggested future schema additions

- `article_chunks`
  - `id`
  - `article_id`
  - `chunk_index`
  - `heading`
  - `content_text`
  - `token_count`
  - `embedding_model`
  - `embedding_created_at`
- `article_recommendations`
  - `source_article_id`
  - `recommended_article_id`
  - `score`
  - `reason`

## Constraints to preserve

- Do not let future retrieval bypass the existing truthfulness and transparency layers.
- Keep provenance for every chunk and embedding generation run.
- Preserve the reader-facing transparency fields even when AI retrieval is introduced.
