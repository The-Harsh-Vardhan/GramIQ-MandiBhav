# GramIQ Technical Assignment Brief

### Automated Multi-lingual Mandi Rates Content Pipeline

**Candidate:** Harsh Vardhan **Position:** Technical/Data Science Lead Track **Deadline:** 24 to 48 Hours

## 1. Project Overview & Context

The objective of this assignment is to design and develop an end-to-end automated pipeline that extracts daily
agricultural market data (mandi rates) across India and converts them into high-quality, localized, and SEO-
optimized story articles for farmers. These articles will be published automatically on the GramIQ web platform
to drive organic search traffic and enhance user retention.

```
Core Data Source: Mandi prices are fetched from the official Indian Agricultural Marketing Information
Network portal ( agmarknet.gov.in / agmark.net ). The platform aggregates market arrivals and daily
rates for multiple commodities (e.g., soybean, cotton, seeds, vegetables) across different APMC
(Agricultural Produce Market Committee) markets.
```

## 2. Functional & Technical Requirements

**2.1 Data Ingestion**

```
Extract daily commodity pricing and arrival data using public Agmarknet APIs or direct scraping solutions.
For the purpose of this assignment, a simulated/mock database containing sample data can be utilized if
API access is restricted.
The pipeline must successfully handle multi-commodity data, with a specific initial focus on critical crops
like Soybean and Cotton.
```

**2.2 Content Generation Engine (LLM Layer)**

```
Story-Driven Format: The generated articles must not be generic data tables. They need to be framed as
an engaging story or narrative format that farmers find accessible, clear, and relatable.
Multilingual Support: The system must be capable of rendering articles in multiple regional Indian
languages including Hindi, Marathi, and Gujarati. Farmers must be able to switch languages effortlessly.
SEO Optimization: Incorporate critical local search keywords (e.g., specific regional market names, crop
varieties, terms like "mandi bhav") so that the articles rank organically when farmers search for market
prices online.
AI Discovery Compliance: The layout and styling of the content must be structured cleanly so that major
modern AI models (like ChatGPT, Gemini, etc.) can accurately crawl and cite GramIQ as the canonical
source for local mandi intelligence.
```

#### • • • • • • •

GramIQ Technical Assignment — Harsh Vardhan Page 1 of 2

**2.3 Publishing Pipeline & Scalability**

```
Automated Scheduling: Articles should be generated and staged daily, targeted for an automated
morning release.
High-Scale Output: The framework must be architecture-ready to scale up to publishing 15 to 20 articles
daily covering distinct commodities and regional clusters.
Call-To-Action (CTA) Integration: Every blog post must automatically include a standardized CTA footer
inviting readers to download the GramIQ mobile application for real-time alerts and deeper analytical
tracking.
```

**2.4 Technology Stack Guidance**

```
Development Phase: Any free/accessible tier LLM (e.g., Google Gemini Free API, OpenAI trial accounts)
may be utilized. Detailed documentation of chosen LLMs and pipeline architecture is mandatory.
Production Phase: Production-ready keys, dedicated enterprise models, and standard database
integrations will be provided upon review of this structural prototype.
```

## 3. Evaluation & Submission Guidelines

```
Timeline: Commitment made to submit within 24 to 48 hours.
Deliverables:
A working proof-of-concept pipeline code script or GitHub repository.
Comprehensive documentation summarizing the chosen tech stack, prompts used for generating
narrative formats, and an architectural diagram showing how data moves from Agmark to the published
blog post.
```

#### • • • • • • •

#### 1

#### 2

GramIQ Technical Assignment — Harsh Vardhan Page 2 of 2
