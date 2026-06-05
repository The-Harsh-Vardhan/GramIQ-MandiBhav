# MandiBhav by GramIQ

## Architecture Evolution

This section documents the architectural evolution of the MandiBhav by GramIQ project, showing how the system evolved from an AI-centric prototype into a data-grounded agricultural intelligence platform.

---

# Version 1 — Naive Architecture (AI-Centric)

```mermaid
flowchart TD

    A[OGD API] --> B[Raw Market Data]

    B --> C[Gemini]

    C --> D[English Article]
    C --> E[Hindi Article]
    C --> F[Marathi Article]

    D --> G[Website]
    E --> G
    F --> G
```

## Characteristics

- AI directly consumes raw data
- No analytics layer
- No validation layer
- No truthfulness checks
- No fallback mechanism
- Multiple language generation

## Problems

- Hallucinations
- Translation drift
- High API usage
- No explainability
- AI became the source of truth

## Key Lesson

> AI should not be the source of truth.

---

# Version 2 — Overengineered Architecture

```mermaid
flowchart TD

    A[OGD API]
    A --> B[Ingestion Layer]

    B --> C[SQLite Database]

    C --> D[Commodity Reports]
    C --> E[State Reports]
    C --> F[Market Reports]
    C --> G[Top Gainers Reports]
    C --> H[Best Market Reports]

    D --> I[Gemini]
    E --> I
    F --> I
    G --> I
    H --> I

    I --> J[English Articles]
    I --> K[Hindi Articles]
    I --> L[Marathi Articles]

    J --> M[Static Website]
    K --> M
    L --> M
```

## Characteristics

- Multiple report types
- Multiple commodities
- Multiple languages
- Heavy AI usage
- SEO-first content generation

## Problems

- 20+ articles per run
- Excessive Gemini API calls
- Long execution times
- Difficult debugging
- Translation inconsistencies
- Scope creep
- Rising infrastructure complexity

## Key Lesson

> A working pipeline is worth more than twenty partially working pipelines.

---

# Version 3 — Analytics-Driven Architecture

```mermaid
flowchart TD

    A[OGD API]

    A --> B[Data Ingestion]

    B --> C[SQLite Database]

    C --> D[Analytics Engine]

    D --> E[Price Statistics]
    D --> F[MSP Comparison]
    D --> G[Historical Comparison]

    E --> H[Fact Package]
    F --> H
    G --> H

    H --> I[Gemini]

    I --> J[English Article]

    J --> K[Static Website]
```

## Improvements

- Analytics layer introduced
- Structured fact generation
- Reduced article generation
- Reduced API costs
- Faster execution
- Improved maintainability

## Remaining Problems

- Unsupported claims
- Hallucinated commentary
- Overconfident reports
- No claim validation

## Key Lesson

> Analytics should transform data into facts before AI sees it.

---

# Version 4 — Truthfulness Architecture

```mermaid
flowchart TD

    A[OGD API]

    A --> B[Data Ingestion]

    B --> C[SQLite Database]

    C --> D[Analytics Engine]

    D --> E[Fact Package]

    E --> F[Gemini]

    F --> G[Generated Article]

    G --> H[Claim Validation]

    H --> I[Contradiction Check]

    I --> J[Scope Validation]

    J --> K[Credibility Score]

    K --> L[Publishing Gate]

    L --> M[Publish]
    L --> N[Review Required]
```

## Improvements

- Truthfulness layer added
- Contradiction detection
- Scope locking
- Credibility scoring
- Publishing gate
- Better transparency

## Remaining Problems

- Translation inconsistencies
- Weak multilingual validation
- Quality reports focused too much on formatting

## Key Lesson

> SEO correctness is not factual correctness.

---

# Version 5 — Final Architecture (Current)

```mermaid
flowchart TD

    A[OGD API]

    A --> B[Ingestion Layer]

    B --> C[Retry Logic]
    B --> D[Timeout Control]
    B --> E[Fallback Handling]

    C --> F[Data Validation]
    D --> F
    E --> F

    F --> G[Date Normalization]
    F --> H[Deduplication]

    G --> I[SQLite Database]
    H --> I

    I --> J[Analytics Engine]

    J --> K[Price Statistics]
    J --> L[MSP Analysis]
    J --> M[Historical Comparison]
    J --> N[Data Quality Metrics]

    K --> O[Fact Package]
    L --> O
    M --> O
    N --> O

    O --> P[Gemini]

    P --> Q[English Price Snapshot Report]

    Q --> R[Claim Validation]
    R --> S[Scope Validation]
    S --> T[Credibility Scoring]

    T --> U[Publishing Gate]

    U --> V[Published]
    U --> W[Review Required]

    V --> X[Static Site Builder]

    X --> Y[HTML]
    X --> Z[Sitemap]
    X --> AA[RSS Feed]
    X --> AB[Search Index]

    Y --> AC[GitHub Pages]
    Z --> AC
    AA --> AC
    AB --> AC
```

## Major Improvements

### Reliability

- Retry logic
- Timeout controls
- Fallback handling
- Historical cache support

### Data Quality

- Date normalization
- Deduplication
- Validation layer

### Analytics

- MSP comparison
- Historical comparison
- Price statistics
- Data quality metrics

### Content

- Single source of truth
- English-only article generation
- Data-grounded reporting

### Trust Layer

- Claim validation
- Scope validation
- Credibility scoring
- Publishing gate

### Publishing

- HTML generation
- Sitemap
- RSS feed
- Search index
- GitHub Pages deployment

## Key Lesson

> AI should transform facts into language, not transform guesses into facts.

---

# Detailed Component Architecture

## Data Layer

```mermaid
flowchart TD

    A[OGD API]

    A --> B[Live Provider]

    B --> C[Retry Logic]
    B --> D[Pagination]
    B --> E[Timeout Control]
    B --> F[Market Filtering]

    C --> G[Normalized Records]
    D --> G
    E --> G
    F --> G
```

### Responsibilities

- API communication
- Pagination
- Retry handling
- Timeout management
- Data filtering
- Data normalization

---

## Analytics Layer

```mermaid
flowchart TD

    A[Market Data]

    A --> B[Analytics Engine]

    B --> C[Min Price]
    B --> D[Max Price]
    B --> E[Modal Price]
    B --> F[MSP Comparison]
    B --> G[Historical Change]
    B --> H[Record Statistics]
```

### Responsibilities

- Convert raw market records into structured facts
- Generate metrics for report generation

---

## Content Layer

```mermaid
flowchart TD

    A[Analytics]

    A --> B[Fact Package]

    B --> C[Gemini]

    C --> D[English Article]
```

### Responsibilities

- Convert facts into human-readable content
- Preserve factual integrity

---

## Trust Layer

```mermaid
flowchart TD

    A[Generated Article]

    A --> B[Claim Validation]

    B --> C[Contradiction Detection]

    C --> D[Scope Validation]

    D --> E[Credibility Scoring]

    E --> F[Publishing Decision]
```

### Responsibilities

- Prevent hallucinations
- Validate claims
- Ensure scope consistency
- Calculate trustworthiness

---

## Publishing Layer

```mermaid
flowchart TD

    A[Validated Article]

    A --> B[HTML Generator]

    B --> C[Sitemap]

    B --> D[RSS Feed]

    B --> E[Search Index]

    C --> F[GitHub Pages]
    D --> F
    E --> F
```

### Responsibilities

- Website generation
- Search indexing
- SEO support
- Deployment

---

# Architecture Evolution Summary

```mermaid
flowchart LR

    A[Version 1<br/>AI-Centric]

    B[Version 2<br/>Overengineered]

    C[Version 3<br/>Analytics-Driven]

    D[Version 4<br/>Truthfulness Layer]

    E[Version 5<br/>Data-Grounded Intelligence]

    A --> B
    B --> C
    C --> D
    D --> E
```

---

# Philosophy Evolution

## Version 1

```mermaid
flowchart TD

    A[Data]

    A --> B[AI]

    B --> C[Publish]
```

### Philosophy

> Data → AI → Publish

---

## Final Version

```mermaid
flowchart TD

    A[Data]

    A --> B[Analytics]

    B --> C[Fact Validation]

    C --> D[AI]

    D --> E[Truthfulness Validation]

    E --> F[Publishing Gate]

    F --> G[Publish]
```

### Philosophy

> Data → Analytics → Validation → AI → Validation → Publish

---

# Final Design Principle

> The data is the source of truth.

> Analytics extracts facts from the data.

> AI transforms facts into human-readable reports.

> Validation ensures that AI never exceeds the evidence provided by the data.

This became the most important architectural decision in the entire project and represents the evolution from an AI-generated content system into a trustworthy agricultural intelligence platform.
