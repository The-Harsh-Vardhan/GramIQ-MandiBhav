# MandiBhav by GramIQ

## Design Decisions, Challenges, Failures, Lessons Learned and Evolution Timeline

---

# Executive Summary

MandiBhav by GramIQ started as an ambitious AI-powered agricultural intelligence platform capable of generating multilingual market reports across multiple commodities, regions, and time horizons.

However, during development, several practical challenges emerged:

- Unreliable government APIs
- AI hallucinations
- Multilingual inconsistencies
- Excessive API costs
- Overly broad project scope
- Misleading confidence metrics
- Poor data grounding

Through multiple iterations, the system evolved from an AI-heavy content generator into a data-first market intelligence platform focused on trustworthiness, transparency, and reliability.

---

# Phase 0 — Original Vision (The First Mistake)

## Initial Idea

Build:

- All Commodities
- All States
- All Languages
- Daily Reports
- AI Insights
- Predictions
- SEO Pages

Essentially:

> "Let's build the agricultural Bloomberg of India."

### Mistake

The assignment required:

> End-to-end AI pipeline demonstration

but the design was heading toward:

> National-scale content platform

### Lesson Learned

The biggest risk was not technology.

The biggest risk was **scope**.

---

# Phase 1 — Overengineering Before Validation

## Initial Design

The first architecture generated:

- Commodity Reports
- State Reports
- Market Reports
- Best Market Reports
- Top Gainer Reports
- Loser Reports
- Trend Reports

for:

- Soybean
- Cotton
- Multiple Regions
- Multiple Languages

### Problem

One run attempted to create:

> 20+ articles

from a single data pull.

### Consequences

- Slow execution
- Excessive API usage
- Difficult debugging
- High Gemini costs

### Design Decision

Reduce:

> Many Reports

to:

> One Report

for demo mode.

### Lesson Learned

A working pipeline is worth more than 20 partially working pipelines.

---

# Phase 2 — The Government API Reality Check

## Assumption

Government API = Reliable Data Source

### Reality

Repeated:

- Connection Timeout
- Read Timeout
- Slow Responses

Sometimes:

- 15 seconds
- 20 seconds
- 30 seconds

for simple requests.

### Mistake

Treating OGD as a production-grade API.

### Solution

Introduced:

- Retry Logic
- Timeout Controls
- Fallback Logic
- Mock Data
- Historical Cache

### Lesson Learned

Never trust external APIs to be available during your demo.

---

# Phase 3 — The "More AI = Better" Mistake

## Assumption

More AI-generated content means a better product.

### Result

Articles included:

- Farmer Sentiment
- Demand Analysis
- Seasonal Trends
- Market Outlook

without any supporting data.

### Example

Data Available:

- Price
- Arrival
- MSP

Article Generated:

> Strong demand from processors.

> Farmers are actively selling.

> Regional sentiment remains bullish.

### Problem

The model invented information.

### Design Decision

Move from:

> AI First

to:

> Data First

### Lesson Learned

Good AI systems know what **not** to say.

---

# Phase 4 — The Translation Disaster

## Original Plan

Generate:

- English
- Hindi
- Marathi

for every report.

### Assumption

Translation is easy.

### Reality

English:

> Arrival = 0

Hindi:

> Strong supply.

Marathi:

> Active trading.

### Worse

- Prices changed
- Percentages changed
- Facts changed

### Root Cause

Translation models rewrote content instead of translating it.

### Design Decision

Single source of truth:

> English Article

Use browser-side translation.

### Lesson Learned

Three articles that disagree are worse than one article.

---

# Phase 5 — The Confidence Score Failure

## Original Idea

Every article gets:

> confidence_score

### Reality

System reported:

> 1.0

even when:

- Mock Data
- Cache
- Fallbacks

were used.

### Problem

Confidence became meaningless.

### Design Decision

Introduce:

> Credibility Score

based on:

- Live data availability
- Record count
- Contradictions
- Unsupported claims
- Fallback usage

### Lesson Learned

Metrics should reflect reality, not pipeline completion.

---

# Phase 6 — The Truthfulness Crisis

## Discovery

Articles could pass all validators while still being wrong.

### Example

Data:

> Arrival = 0

Article:

> Substantial influx of supply.

### Problem

Validators checked:

> Formatting

instead of:

> Truthfulness

### Solution

Introduced:

- Claim Support Validation
- Contradiction Detection
- Scope Validation

### Lesson Learned

SEO correctness is not factual correctness.

---

# Phase 7 — The Scope Leakage Problem

## Observation

Nagpur report discussed:

- Maharashtra
- Regional Markets
- National Trends

despite only having Nagpur data.

### Root Cause

Prompts encouraged broad commentary.

### Solution

Created:

> Scope Locking

Rules:

```text
Nagpur Data
→ Nagpur Commentary

State Data
→ State Commentary

National Data
→ National Commentary
```

### Lesson Learned

Data scope and narrative scope must match.

---

# Phase 8 — The One-Record Intelligence Problem

## Observation

Single market record.

Article still generated:

- Market Trends
- Future Outlook
- Demand Analysis

### Problem

Insufficient evidence.

### Design Decision

Introduce:

- PRICE_SNAPSHOT
- MARKET_REPORT
- TREND_REPORT

### Lesson Learned

Report type should reflect available evidence.

---

# Phase 9 — Database and Cleanup Failures

## Problem

Experiments polluted future experiments.

Old data remained.

Caches remained.

Reports remained.

### Example

Running:

```bash
clear_date.py
```

sometimes deleted:

> 0 rows

because date formats differed.

### Root Cause

Inconsistent date handling.

### Solution

Standardized:

```text
YYYY-MM-DD
```

everywhere.

### Lesson Learned

Developer tooling matters.

---

# Phase 10 — Historical Backfill Decision

## Problem

Website looked empty.

Homepage:

> 1 Article

### Decision

Generate:

- Past 7 Days
- Past 14 Days
- Custom Range

### Benefit

- Site appears realistic
- Archive works
- Search becomes useful

### Lesson Learned

Perceived completeness matters.

---

# Phase 11 — Observability and Logging

## Early State

Logs were noisy:

```text
Skipped Duplicate
Skipped Duplicate
Skipped Duplicate
```

hundreds of times.

### Problem

Hard to debug.

### Solution

Aggregate metrics:

```text
Inserted: X
Duplicates: Y
```

Add:

- Unique Markets
- Unique Varieties
- Unique Grades

### Lesson Learned

Logs should explain, not overwhelm.

---

# Phase 12 — Final Architecture

## Final Philosophy

```text
Live Data
↓
Analytics
↓
Claim Validation
↓
Article Generation
↓
Credibility Scoring
↓
Publishing Gate
↓
GitHub Pages
```

Not:

```text
Data
↓
AI
↓
Hope
```

😂

---

# Additional Design Decisions and Tradeoffs

## Why GitHub Pages?

### Alternatives Considered

- Vercel
- Netlify
- Render

### Decision

GitHub Pages

### Reason

- Free
- Simple
- Static hosting
- Easy deployment
- Good for assignment demos

---

## Why SQLite?

### Alternatives Considered

- PostgreSQL
- MongoDB
- Supabase

### Decision

SQLite

### Reason

- Zero setup
- Local development
- Fast enough for demo scale
- Easier debugging

---

## Why Single English Article?

### Alternatives Considered

- English + Hindi + Marathi
- Fully multilingual generation

### Decision

English only

### Reason

- Eliminates translation inconsistency
- Reduces API calls
- Maintains factual integrity
- Simplifies validation

---

## Why Historical Backfill?

### Alternatives Considered

Generate only today's report.

### Problem

The website felt empty.

### Decision

Generate historical reports.

### Benefit

- Archive pages
- Better SEO
- Better presentation
- More realistic website

---

## Why Not AI Predictions?

### Original Plan

Predict future prices.

### Problem

No supporting predictive model existed.

### Decision

Remove predictions entirely.

### Lesson

Reliable observation is better than unreliable prediction.

---

# Biggest Lessons Learned

## 1. Scope Is The Hardest Engineering Problem

Most technical issues originated from trying to do too much.

---

## 2. AI Should Summarize Data, Not Invent It

The best reports came from restricting the model.

---

## 3. Reliability Beats Sophistication

A simple pipeline that always works is more valuable than a complex one that occasionally fails.

---

## 4. Translation Is Harder Than Expected

Especially when facts and numbers must remain identical.

---

## 5. Truthfulness Requires Explicit Engineering

Better prompts alone do not solve hallucination.

Validation layers are required.

---

## 6. Developer Tooling Is Part Of The Product

Date normalization, cleanup scripts, caching, and logging saved more time than prompt engineering.

---

## 7. Observability Matters

Without proper logs, debugging becomes guesswork.

---

## 8. User Trust Is More Important Than Fancy Features

A smaller but truthful report is better than a larger but misleading report.

---

# Final Conclusion

The development of MandiBhav by GramIQ was not a straight line.

The project evolved through multiple cycles of experimentation, failure, redesign, and simplification.

The most important realization was that the goal was not to generate as much content as possible.

The goal was to generate content that could be trusted.

The system evolved from:

```text
AI Agricultural News Generator
```

into:

```text
Data-Grounded Agricultural Intelligence Platform
```

The final product is smaller than the original vision, but significantly more reliable, explainable, and suitable for real-world deployment and demonstration.

In the end, the most valuable engineering decision was not adding more AI.

It was learning where AI should stop.
