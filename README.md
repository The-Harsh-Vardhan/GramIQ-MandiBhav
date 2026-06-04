# MandiBhav by GramIQ

> **Automated Multi-Lingual Mandi Rates Content Pipeline**
> 
> Generates 15–20 SEO-optimized agricultural market articles daily in 4 languages (English, Hindi, Marathi, Gujarati), grounded in real mandi price data, with structured JSON-LD schema output.

---

## Quick Start (2 minutes)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Gemini API key
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 3. Run the pipeline (dev mode — no OGD API key needed)
python main.py

# 4. View generated articles
ls output/2026-06-04/
```

**The pipeline runs end-to-end without any API keys in dev mode.** Only `GEMINI_API_KEY` is required for article generation.

---

## Architecture Overview

```
python main.py
      │
      ├── Stage 1: Ingest ──────────────────────────────────────────────
      │   MockProvider (CSV)  ──or──  LiveProvider (OGD API)
      │   → SQLite market_data table (deduplicated via UNIQUE constraint)
      │
      ├── Stage 2: Analytics ───────────────────────────────────────────
      │   pandas pre-computation:
      │   • National avg modal price + day-over-day delta
      │   • State-wise aggregations
      │   • Top/bottom markets by price and arrival volume
      │   • Top gainers & losers (day-over-day)
      │   Knowledge injection:
      │   • MSP vs current price (% above/below)
      │   • Seasonal phase and context (sowing / harvest / lean)
      │   • Market significance notes
      │   → scope_matrix: list of articles to generate
      │
      ├── Stage 3: Generate + Translate + Assemble ─────────────────────
      │   For each scope target:
      │   1. Build 3-layer prompt (system + analytics context + article type)
      │   2. Gemini API → structured JSON output
      │   3. Pydantic validation + retry with error correction
      │   4. Gemini translation → HI, MR, GU (HTML-preserving)
      │   5. Confidence scoring (6-signal heuristic gate)
      │   6. Render JSON-LD (NewsArticle + FAQPage) via Jinja2
      │   7. Write JSON files to output/{date}/{scope_key}/{lang}.json
      │
      └── Stage 4: Evaluate ────────────────────────────────────────────
          Scan all output JSON files → compute 13 KPIs
          Print quality report + write output/{date}/quality_report.json
```

### Module Dependency Graph

```
config.py ←── schemas.py
    ↓               ↑
database.py    ingestion.py → analytics.py
                                   ↓
                             llm_engine.py
                                   ↓
                             translator.py
                                   ↓
                           seo_assembler.py
                                   ↓
                             evaluate.py
                                   ↓
                               main.py
```

No circular dependencies. Each module has a single responsibility.

---

## CLI Reference

```bash
python main.py [OPTIONS]

Options:
  --date YYYY-MM-DD      Target date (default: today)
  --mode dev|live        Pipeline mode (default: from PIPELINE_MODE env var)
  --commodities soybean cotton  Specific commodities (default: all)
  --skip-translate       Generate English only (faster dev loop)
  --evaluate-only        Re-evaluate existing output without regenerating
  --skip-evaluate        Skip post-run quality report
  --verbose              Enable DEBUG logging
```

**Examples:**
```bash
# Full run, today, dev mode (recommended for demo)
python main.py

# Specific date
python main.py --date 2026-06-04

# English only (fast, no translation API calls)
python main.py --skip-translate

# Live API mode
python main.py --mode live

# Single commodity
python main.py --commodities soybean

# Re-evaluate existing output
python main.py --date 2026-06-04 --evaluate-only
```

---

## Article Types (5 MVP families)

| Type | Description | Daily Count | SEO Intent |
|---|---|---|---|
| **Daily Commodity Report** | National overview of one commodity | 2 | "soybean mandi bhav today" |
| **State Market Report** | All markets in one state for one commodity | ~9 | "soybean bhav Maharashtra today" |
| **Market Spotlight** | Deep-dive into one high-volume APMC | 4 | "Mandsaur mandi bhav today" |
| **Best Market Today** | Direct advisory: where to sell now | 2 | "best mandi for soybean today" |
| **Top Gainers & Losers** | Momentum report: biggest movers | 2 | "soybean price up today" |
| **Total English articles** | | **~19** | |
| **Total with 4 languages** | | **~76 JSON files** | |

---

## Output Format

Each generated article is written as a JSON file:

```
output/
└── 2026-06-04/
    ├── soybean_national/
    │   ├── en.json         ← English
    │   ├── hi.json         ← Hindi
    │   ├── mr.json         ← Marathi
    │   └── gu.json         ← Gujarati
    ├── cotton_maharashtra/
    │   ├── en.json
    │   └── ...
    ├── review/             ← Articles scoring 0.40-0.74 (manual review)
    ├── blocked/            ← Articles scoring <0.40 (generation failed)
    └── quality_report.json ← Pipeline KPI summary
```

**Article JSON structure:**
```json
{
  "title": "Soybean Mandi Bhav Today, 4 June 2026: National Average at ₹5,100",
  "meta_description": "Soybean prices averaged ₹5,100/quintal across India on 4 June 2026...",
  "body": "<h2>...</h2><p>...</p>",
  "keywords": ["soybean mandi bhav today", "soyabean bhav"],
  "language": "en",
  "date": "2026-06-04",
  "commodity": "soybean",
  "article_type": "daily_commodity_report",
  "scope_key": "soybean_national",
  "json_ld": { "@context": "https://schema.org", "@type": "NewsArticle", ... },
  "faq_json_ld": { "@context": "https://schema.org", "@type": "FAQPage", ... },
  "faqs": [
    { "question": "What is today's soybean price?", "answer": "..." }
  ],
  "confidence_score": 0.875,
  "publish_status": "published",
  "generated_at": "2026-06-04T06:12:34Z"
}
```

---

## Quality Report (Sample)

```
═══════════════════════════════════════════════════════
  MandiBhav Quality Report — 2026-06-04
═══════════════════════════════════════════════════════

  PIPELINE
  ├── Total files:              76
  ├── Published (≥0.75):        72  ✅
  ├── Review Required (0.40-0.74): 4
  ├── Blocked (<0.40):          0
  └── Pipeline time:            6m 12s

  CONTENT
  ├── Avg word count:           482 words
  ├── Word count OK:            97.4%  ✅
  ├── CTA present:              100.0%  ✅
  └── Avg FAQs per article:     2.6

  SEO
  ├── Keyword in title:         100.0%  ✅
  ├── Title length OK:          94.7%  ✅
  ├── Meta desc length OK:      97.4%  ✅
  ├── Has H2 headings:          100.0%  ✅
  ├── JSON-LD NewsArticle OK:   100.0%  ✅
  └── JSON-LD FAQPage OK:       100.0%  ✅

  CONFIDENCE
  ├── Average:                  0.841
  ├── Minimum:                  0.550
  └── Maximum:                  1.000

  OUTPUT: output/2026-06-04/
═══════════════════════════════════════════════════════
```

---

## Knowledge Layer

The pipeline injects contextual domain knowledge into every prompt — not as data, but as interpretation context.

| File | Purpose | Example |
|---|---|---|
| `data/knowledge/msp_rates.json` | Government MSP by crop and year | Soybean MSP 2025-26: ₹4,892 |
| `data/knowledge/commodity_profiles.json` | Seasonality, key states, multilingual names | June = kharif sowing season |
| `data/knowledge/market_profiles.json` | APMC significance, typical volumes | Mandsaur = largest soybean market in Asia |
| `data/knowledge/seasonal_calendar.json` | Month-by-month seasonal context | November = peak arrivals, prices at seasonal low |

This transforms generic "price went up 1.25%" articles into:
> *"At ₹5,100, soybean is trading 4.3% above the MSP of ₹4,892, signaling healthy returns for farmers in the ongoing kharif sowing season. Mandsaur — Asia's largest soybean market — led the day with ₹620 tonnes arriving at ₹5,100/quintal."*

---

## Confidence Scoring

Every article receives a heuristic quality score before publishing:

| Signal | Weight | Check |
|---|---|---|
| Data Coverage | 0.20 | ≥2 reporting markets for this scope |
| Numeric Integrity | 0.25 | All key analytics numbers appear in article |
| Price Anomaly | 0.20 | Day-over-day change ≤ ±25% |
| Output Validity | 0.15 | Word count 200-1000, has H2 + `<p>` tags, ≥2 FAQs |
| Translation QA | 0.10 | Numeric preservation passes in all translations |
| Keyword Coverage | 0.10 | Required keywords found in title+body |

**Publishing thresholds:**
- Score ≥ 0.75 → Auto-published to `output/{date}/{scope}/`
- Score 0.40-0.74 → Review required → `output/{date}/review/`
- Score < 0.40 → Blocked → `output/{date}/blocked/`

---

## Dev Mode vs Live Mode

| | Dev Mode (`PIPELINE_MODE=dev`) | Live Mode (`PIPELINE_MODE=live`) |
|---|---|---|
| **Data source** | CSV fixtures in `data/mock/` | data.gov.in OGD REST API |
| **API keys needed** | Only `GEMINI_API_KEY` | `GEMINI_API_KEY` + `OGD_API_KEY` |
| **Reproducible** | ✅ Yes — same CSV, same analytics | ❌ Varies by day |
| **Offline** | ✅ Yes | ❌ No |
| **Switching** | `PIPELINE_MODE=live` in `.env` | `PIPELINE_MODE=dev` in `.env` |

---

## Running Tests

```bash
# Install pytest first
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_analytics.py -v
pytest tests/test_ingestion.py -v
```

---

## Project Structure

```
gramiq-mandibhav/
├── config.py              # Settings, paths, knowledge loaders
├── schemas.py             # All Pydantic models
├── database.py            # SQLite init, insert, query helpers
├── ingestion.py           # DataProvider ABC, MockProvider, LiveProvider
├── analytics.py           # Pandas pre-computation + scope matrix
├── llm_engine.py          # Gemini API client + 3-layer prompt builder
├── translator.py          # Gemini translation + QA checks
├── seo_assembler.py       # Confidence scoring + JSON-LD + file writer
├── evaluate.py            # Post-run quality metrics + report
├── main.py                # CLI entry point + pipeline orchestrator
│
├── data/
│   ├── mock/              # CSV fixtures for dev mode
│   │   ├── soybean_sample.csv
│   │   ├── soybean_previous_day.csv
│   │   ├── cotton_sample.csv
│   │   └── cotton_previous_day.csv
│   ├── knowledge/         # Static domain knowledge (injected into prompts)
│   │   ├── msp_rates.json
│   │   ├── commodity_profiles.json
│   │   ├── market_profiles.json
│   │   └── seasonal_calendar.json
│   └── fixtures/
│       └── commodities.json
│
├── templates/
│   ├── prompts/
│   │   ├── system_prompt.txt       # LLM persona + hard constraints
│   │   ├── article_types.json      # 5 article type templates
│   │   └── translation_prompt.txt  # HTML-preserving translation prompt
│   └── seo/
│       ├── jsonld_article.j2       # NewsArticle JSON-LD template
│       └── jsonld_faq.j2           # FAQPage JSON-LD template
│
├── tests/
│   ├── test_analytics.py  # Analytics + knowledge injection tests
│   └── test_ingestion.py  # MockProvider + schema validation tests
│
├── output/                # Generated articles (git-ignored)
├── mandibhav.db           # SQLite database (git-ignored)
├── requirements.txt       # 6 dependencies
├── .env.example           # Environment variable template
└── README.md
```

---

## Scaling Roadmap

| Scale | Changes Required |
|---|---|
| **20 articles/day (current)** | SQLite, sequential, Gemini free tier |
| **100 articles/day** | SQLite still fine; paid Gemini tier (~$0.50/day) |
| **1,000 articles/day** | PostgreSQL, async pipeline, Bhashini translation |
| **10,000+ articles/day** | Celery workers, Redis cache, CDN distribution |

---

## Dependencies

```
google-generativeai    # Gemini API client
pydantic               # Data validation
pandas                 # Statistical pre-computation
jinja2                 # JSON-LD template rendering
tenacity               # Exponential backoff retries
requests               # OGD API calls (live mode)
```

All 6 packages. No web framework, no database server, no message queue.

---

## Assignment Checklist

- [x] Automated data ingestion (OGD API + CSV mock fallback)
- [x] Multi-commodity support (Soybean + Cotton)
- [x] Pre-computed analytics (prevents LLM hallucination)
- [x] Knowledge-grounded articles (MSP, seasonality, market context)
- [x] Structured LLM generation (Gemini JSON mode + Pydantic validation)
- [x] 5 article types with distinct prompts (15-20/day target)
- [x] 4 language support (EN, HI, MR, GU)
- [x] FAQ generation for AI discoverability
- [x] JSON-LD NewsArticle schema (required)
- [x] JSON-LD FAQPage schema (AI discoverability)
- [x] Confidence scoring + publishing gate
- [x] Mock data mode (clone-and-run without API keys)
- [x] Quality evaluation report (self-grading pipeline)
- [x] GramIQ CTA footer in all articles
- [x] SQLite for data storage (no server required)
- [x] Unit tests for analytics and ingestion
- [x] Clean modular architecture (10 files, no circular deps)

---

*Built for GramIQ Assignment — June 2026*
