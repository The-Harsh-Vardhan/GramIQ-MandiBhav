create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create table if not exists public.articles (
    id text primary key,
    slug text not null,
    title text not null,
    article_date date not null,
    commodity_slug text not null,
    market_name text,
    state text,
    language text not null default 'en',
    body_html text not null,
    meta_description text not null,
    seo_title text not null,
    credibility_score numeric(5, 3) not null default 0,
    data_source text not null default 'LIVE',
    report_type text not null default 'PRICE_SNAPSHOT',
    publish_status text not null default 'draft',
    scope_key text not null,
    article_type text not null,
    json_ld jsonb not null default '{}'::jsonb,
    faq_json_ld jsonb not null default '{}'::jsonb,
    faqs jsonb not null default '[]'::jsonb,
    keywords jsonb not null default '[]'::jsonb,
    records_analyzed integer not null default 0,
    contradictions_count integer not null default 0,
    unsupported_claims_count integer not null default 0,
    scope_violations_count integer not null default 0,
    truthfulness_score numeric(5, 3) not null default 1,
    data_source_disclosure_present boolean not null default true,
    fallback_disclosure_present boolean not null default true,
    unique_markets_count integer not null default 0,
    unique_varieties_count integer not null default 0,
    unique_grades_count integer not null default 0,
    pipeline_run_id text,
    ai_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create unique index if not exists idx_articles_slug_language
    on public.articles (slug, language);

create index if not exists idx_articles_publish_date
    on public.articles (publish_status, article_date desc);

create index if not exists idx_articles_commodity_date
    on public.articles (commodity_slug, article_date desc);

create index if not exists idx_articles_market
    on public.articles (market_name, state);

create index if not exists idx_articles_search_title
    on public.articles using gin (title gin_trgm_ops);

create index if not exists idx_articles_search_description
    on public.articles using gin (meta_description gin_trgm_ops);

create index if not exists idx_articles_search_body
    on public.articles using gin (body_html gin_trgm_ops);

create table if not exists public.market_data (
    id bigserial primary key,
    commodity_slug text not null,
    market_date date not null,
    state text not null,
    district text not null default '',
    market_name text not null,
    variety text not null default '',
    grade text not null default '',
    min_price numeric(12, 2) not null default 0,
    max_price numeric(12, 2) not null default 0,
    modal_price numeric(12, 2) not null,
    arrival_tonnes numeric(12, 2) not null default 0,
    source text not null default 'ogd',
    raw_payload jsonb not null default '{}'::jsonb,
    ingested_at timestamptz not null default timezone('utc', now())
);

create unique index if not exists idx_market_data_unique
    on public.market_data (
        commodity_slug,
        market_date,
        state,
        market_name,
        variety,
        grade
    );

create index if not exists idx_market_data_date
    on public.market_data (market_date desc);

create index if not exists idx_market_data_lookup
    on public.market_data (commodity_slug, state, market_name);

create table if not exists public.pipeline_runs (
    id text primary key,
    run_date date not null,
    mode text not null,
    status text not null default 'running',
    records_processed integer not null default 0,
    articles_generated integer not null default 0,
    articles_review integer not null default 0,
    articles_blocked integer not null default 0,
    total_duration_seconds numeric(12, 2) not null default 0,
    created_at timestamptz not null default timezone('utc', now()),
    completed_at timestamptz
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists trg_articles_updated_at on public.articles;
create trigger trg_articles_updated_at
before update on public.articles
for each row
execute function public.set_updated_at();

alter table public.articles enable row level security;
alter table public.market_data enable row level security;
alter table public.pipeline_runs enable row level security;

drop policy if exists "published_articles_read" on public.articles;
create policy "published_articles_read"
on public.articles
for select
to anon, authenticated
using (publish_status = 'published');

drop policy if exists "market_data_read" on public.market_data;
create policy "market_data_read"
on public.market_data
for select
to anon, authenticated
using (true);
