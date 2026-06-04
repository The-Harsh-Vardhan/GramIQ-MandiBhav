# Static Site Generator Extension — Implementation Plan

## Goal
Extend the existing MandiBhav pipeline with a `build_site.py` module that converts
generated article JSON files into a deployable static website hosted on GitHub Pages.
The existing pipeline is **not modified** — this is purely additive.

---

## Updated Architecture

```
OGD API / Mock CSV
        ↓
  Analytics Engine  ← Knowledge Layer (MSP, seasonal, market profiles)
        ↓
  Prompt Builder
        ↓
     Gemini API
        ↓
 Pydantic Validation
        ↓
    Translation (HI / MR / GU)
        ↓
   SEO Assembler  → JSON-LD, FAQPage
        ↓
  output/{date}/{scope}/{lang}.json         ← EXISTING PIPELINE STOPS HERE
        ↓
  ═══════════════════════════════════
  build_site.py  [NEW]
  ═══════════════════════════════════
        ↓ reads all JSON files in output/
        ↓
   Article Registry (in-memory index)
        ↓
   Jinja2 HTML Rendering
        ↓
   site/ directory
        │
        ├── index.html
        ├── {commodity}/{scope-slug}/index.html
        ├── hi/ mr/ gu/ (language mirrors)
        ├── sitemap.xml
        ├── rss.xml
        └── search.json
        ↓
  GitHub Actions CI/CD
        ↓
  GitHub Pages (gh-pages branch)
```

---

## URL Strategy

| URL Pattern | Maps To | Example |
|---|---|---|
| `/` | Homepage (latest EN articles) | `site/index.html` |
| `/{commodity}/` | Commodity index (EN) | `site/soybean/index.html` |
| `/{commodity}/{scope-slug}/` | Individual EN article | `site/soybean/madhya-pradesh/index.html` |
| `/{lang}/` | Language homepage | `site/hi/index.html` |
| `/{lang}/{commodity}/` | Commodity in language | `site/hi/soybean/index.html` |
| `/{lang}/{commodity}/{scope-slug}/` | Translated article | `site/hi/soybean/madhya-pradesh/index.html` |

**Slug generation rule:** `scope_key` → strip commodity prefix → replace `_` with `-`  
Example: `soybean_madhya_pradesh` → `madhya-pradesh`

**Canonical:** All translated pages reference the EN version as canonical via `<link rel="canonical">`.  
**hreflang:** Each article page includes `<link rel="alternate" hreflang="...">` for all available languages.

---

## MVP Prioritization

| Feature | Priority | Reason |
|---|---|---|
| Article HTML pages | **Must Have** | Core deliverable |
| Commodity index pages | **Must Have** | Navigation + SEO |
| Homepage | **Must Have** | Entry point + branding |
| sitemap.xml | **Must Have** | SEO crawlability |
| SEO meta + OG + JSON-LD | **Must Have** | Already in JSON, just render |
| search.json + client-side search | **Nice to Have** | Demo value |
| rss.xml | **Nice to Have** | Completeness |
| Language switcher UI | **Nice to Have** | Multilingual demo |
| Date archives | Phase 2 | Over-engineering for PoC |
| Related articles | Phase 2 | Requires similarity scoring |
| Tag pages | Phase 2 | Not in scope |

---

## Open Questions

> [!IMPORTANT]
> **GitHub Pages base URL**: Do you have a custom domain, or will the site be at
> `https://The-Harsh-Vardhan.github.io/GramIQ-MandiBhav/`?
> This affects all `href` and `src` paths. The implementation will use a configurable
> `SITE_BASE_URL` in `config.py`.

> [!IMPORTANT]
> **Output date to publish**: The site generator needs to know which date's articles
> to publish. Strategy: build from the **latest date** in `output/` by default.
> Override with `--date YYYY-MM-DD` flag on `build_site.py`.

> [!NOTE]
> **GitHub Actions secrets**: The deployment workflow needs `GEMINI_API_KEY` as a
> GitHub Actions secret. The pipeline will skip generation if not set and only build
> the site from existing JSON files.

---

## Proposed Changes

---

### Configuration

#### [MODIFY] [config.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/config.py)
Add:
- `SITE_DIR`: `ROOT_DIR / "site"`
- `SITE_BASE_URL`: from env var `SITE_BASE_URL`, default `""` (relative URLs)
- `SITE_TITLE`: `"MandiBhav by GramIQ"`
- `SITE_DESCRIPTION`: meta description for homepage

---

### Templates

All new templates go in `templates/site/`. They extend a shared `base.html`.

#### [NEW] `templates/site/base.html`
Full-page layout with:
- `<head>`: charset, viewport, title, meta description, OG tags, JSON-LD slot, hreflang links, CSS
- `<nav>`: GramIQ logo, commodity links (Soybean / Cotton), language switcher
- `<main>`: `{% block content %}`
- `<footer>`: attribution, data source, generated timestamp

**Key template variables:**
```
{{ page_title }}         — <title> tag content
{{ meta_description }}   — <meta name="description">
{{ og_title }}           — Open Graph title
{{ og_description }}     — Open Graph description
{{ og_image_url }}       — og:image (static asset path)
{{ canonical_url }}      — <link rel="canonical">
{{ hreflang_links }}     — list of {lang, url} for alternate links
{{ json_ld_blocks }}     — list of JSON-LD dicts to render as <script type="application/ld+json">
{{ current_lang }}       — "en" | "hi" | "mr" | "gu"
{{ base_url }}           — site root URL
{{ generated_at }}       — build timestamp
```

#### [NEW] `templates/site/homepage.html`
Extends `base.html`.

Variables:
```
{{ latest_date }}        — "June 4, 2026"
{{ commodities }}        — [{"name": "Soybean", "slug": "soybean", "article_count": 12}]
{{ recent_articles }}    — list of last 6 published EN articles (title, url, commodity, type)
{{ stats }}              — {"total_articles": 76, "languages": 4, "markets": 25}
```

Layout sections:
1. Hero banner — headline + latest update badge
2. Commodity cards — Soybean / Cotton with article counts
3. Recent articles grid — 6-card layout
4. "How it works" — 4-step pipeline explainer (data → analytics → AI → publish)

#### [NEW] `templates/site/commodity.html`
Extends `base.html`. One page per commodity (EN + translated).

Variables:
```
{{ commodity }}          — {"name": "Soybean", "slug": "soybean", "description": "..."}
{{ article_groups }}     — grouped by article_type:
                           [{"type_label": "National Report", "articles": [...]}]
{{ latest_date }}        — date of most recent articles
{{ msp_info }}           — {"year": "2025-26", "value": 4892, "commodity": "soybean"}
```

#### [NEW] `templates/site/article.html`
Extends `base.html`. One page per article per language.

Variables:
```
{{ article }}            — full FinalArticleJSON dict
{{ article.title }}
{{ article.meta_description }}
{{ article.body }}       — rendered HTML body (injected directly, already sanitised)
{{ article.faqs }}       — [{"question": ..., "answer": ...}]
{{ article.json_ld }}    — NewsArticle dict
{{ article.faq_json_ld }}— FAQPage dict
{{ article.date }}
{{ article.commodity }}
{{ article.confidence_score }}
{{ market_table }}       — from article.body (extracted) or article.market_summary_table
{{ breadcrumbs }}        — [{"label": "Home", "url": "/"}, {"label": "Soybean", ...}]
{{ available_langs }}    — [{"code": "hi", "label": "हिंदी", "url": "/hi/soybean/..."}]
```

Layout:
1. Breadcrumb nav
2. Article header (title, date badge, commodity tag, confidence badge)
3. Quick summary box (meta_description, styled as a callout)
4. Market price table (extracted from body or market_summary_table)
5. Main article body (the `body` HTML)
6. FAQ accordion (rendered from `faqs` list)
7. Language switcher panel
8. Source attribution footer
9. JSON-LD scripts (NewsArticle + FAQPage)

---

### Site Generator

#### [NEW] [build_site.py](file:///c:/D%20Drive/Projects/Summers%202026/GramIQ%20MandiBhav/build_site.py)

**Workflow:**
```
1. Parse args (--date, --output-dir, --site-dir, --base-url)
2. Discover: scan output/ for all published JSON files
3. Build registry: load all articles into memory, indexed by (scope_key, lang, date)
4. Determine target date (latest or specified)
5. Render: for each (article, lang) → HTML file in site/
6. Render: commodity index pages (EN + translated)
7. Render: homepage (EN)
8. Render: language homepages (hi, mr, gu)
9. Generate: sitemap.xml
10. Generate: rss.xml (latest 20 EN articles)
11. Generate: search.json
12. Copy: static assets (style.css, search.js, favicon)
13. Print: build summary
```

**Key functions:**
- `discover_articles(output_dir, date) → list[dict]`
- `build_article_registry(articles) → dict`
- `render_article_page(article, registry, env) → str`
- `render_commodity_page(commodity, articles, env) → str`
- `render_homepage(registry, env) → str`
- `generate_sitemap(registry, base_url) → str`
- `generate_rss(articles, base_url) → str`
- `generate_search_json(registry) → str`
- `write_site(site_dir, pages) → None`

---

### Static Assets

#### [NEW] `templates/site/assets/style.css`
Clean, modern CSS:
- CSS custom properties for theming (GramIQ green + wheat gold palette)
- Responsive grid for article cards
- Market price table styling
- FAQ accordion (CSS-only, no JS required)
- Language switcher pill buttons
- Confidence score badge colors (green/amber/red)

#### [NEW] `templates/site/assets/search.js`
Vanilla JS client-side search:
- Loads `search.json` on page load
- Filters by title substring match on keypress
- Renders matching articles as cards below the search box
- No external dependencies (no Fuse.js — keeps it truly static)

---

### GitHub Actions

#### [MODIFY] `.github/workflows/ci.yml`
Add a separate `deploy` job that:
1. Runs `main.py` (article generation)
2. Runs `build_site.py` (HTML generation)
3. Commits `site/` to `gh-pages` branch
4. GitHub Pages serves from `gh-pages` branch

#### [NEW] `.github/workflows/deploy.yml`
Dedicated daily deployment workflow (separate from CI tests).

---

### Output Directory

**Generated `site/` layout:**
```
site/
├── index.html
├── soybean/
│   ├── index.html
│   ├── national/index.html
│   ├── madhya-pradesh/index.html
│   ├── maharashtra/index.html
│   ├── mandsaur-spotlight/index.html
│   ├── best-market-today/index.html
│   └── gainers-losers/index.html
├── cotton/
│   ├── index.html
│   ├── national/index.html
│   ├── gujarat/index.html
│   └── ...
├── hi/
│   ├── index.html
│   ├── soybean/index.html
│   └── soybean/{scope}/index.html
├── mr/ (same structure)
├── gu/ (same structure)
├── sitemap.xml
├── rss.xml
├── search.json
└── assets/
    ├── style.css
    ├── search.js
    └── favicon.ico
```

---

## Final Design Review

### What this adds (net complexity)
| Item | Complexity | Value |
|---|---|---|
| `build_site.py` | Low — pure file I/O + Jinja2 | Very High |
| 4 HTML templates | Medium — CSS-heavy | Very High |
| sitemap.xml | Trivial | High (SEO) |
| rss.xml | Trivial | Medium |
| search.json + JS | Low | High (demo) |
| GitHub Actions deploy | Low | Very High |

### Risks
1. **`site/` vs `output/`**: `site/` should be committed to `gh-pages` branch, NOT to `main`. The deploy workflow must `git worktree` or use `peaceiris/actions-gh-pages` to isolate this.
2. **Rate limits**: The GitHub Actions daily run will hit the same Gemini free-tier 20 req/day limit. Mitigation: cache generated JSON and only re-generate if the date has changed.
3. **Relative vs absolute URLs**: If the GitHub Pages URL has a subdirectory path (e.g. `/GramIQ-MandiBhav/`), all asset and page hrefs must be prefixed. The `SITE_BASE_URL` config var solves this.

### Hidden assumptions
- `output/` JSON files always have `publish_status == "published"` for site inclusion
- The `body` field is already sanitized HTML (it is — generated by Gemini with Pydantic validation)
- GitHub Pages is already enabled on the repository settings (free for public repos)

### Verdict: Build it
**Complexity added: Low. Demo value: Very High.**  
The entire extension is ~500 lines of Python (build_site.py) + ~600 lines of HTML/CSS templates.  
It transforms a CLI tool into a *live, browsable, SEO-indexed website* — which is the difference between a "working PoC" and an "impressive submission."

---

## Verification Plan

### Automated
```bash
python build_site.py --date 2026-06-04
# Verify site/ directory created
# Verify sitemap.xml contains all article URLs
# Verify search.json is valid JSON
python -m pytest tests/ -v  # Existing tests still pass
```

### Manual
- Open `site/index.html` in browser — verify homepage renders
- Open an article page — verify JSON-LD is present in `<head>`
- Open `sitemap.xml` — validate against https://www.xml-sitemaps.com/validate-xml-sitemap.html
- Check OG tags with https://opengraph.xyz/

### GitHub Pages
- Push to `gh-pages` branch manually first
- Verify deployment at `https://The-Harsh-Vardhan.github.io/GramIQ-MandiBhav/`
