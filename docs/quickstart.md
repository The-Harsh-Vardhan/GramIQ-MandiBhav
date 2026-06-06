# MandiBhav by GramIQ — Quickstart & Developer Setup Guide

This guide provides step-by-step instructions to set up, configure, run, and test the MandiBhav automated content pipeline.

---

## 1. Prerequisites

Ensure you have the following installed on your system:
- **Python 3.10+** (Python 3.13 recommended)
- **Git**
- **Supabase Account & Project** (for the target database architecture)
- **API Keys**:
  - [Gemini API Key](https://aistudio.google.com/) (for content generation and translation)
  - [OGD India API Key](https://data.gov.in/) (for fetching live daily mandi prices)

---

## 2. Installation & Environment Setup

1. **Clone the repository** (if not already done):
   ```bash
   git clone https://github.com/the-harsh-vardhan/GramIQ-MandiBhav.git
   cd GramIQ-MandiBhav
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

4. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 3. Configuration (`.env`)

Copy the starter template:
```bash
copy .env.example .env
```
*(On macOS/Linux, use `cp .env.example .env`)*

Open `.env` and fill in your details:
```dotenv
# Gemini Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Pipeline Mode: "dev" (local sqlite/mock data) or "live" (OGD API + Supabase)
PIPELINE_MODE=live

# OGD API Configuration
OGD_API_KEY=your_ogd_api_key_here
OGD_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
OGD_PAGE_LIMIT=1000

# Connection settings
OGD_CONNECT_TIMEOUT=10
OGD_READ_TIMEOUT=45

# Data & Publishing backend
DATA_BACKEND=supabase
PUBLISHING_TARGET=vercel
WRITE_ARTICLE_ARTIFACTS=false

# Supabase Configurations
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_public_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_secret_service_role_key_here
SUPABASE_REQUEST_TIMEOUT=30

# Public site deployment URL
PUBLIC_SITE_URL=https://your-mandi-bhav-site.vercel.app
```

---

## 4. Database Setup (Supabase)

The target architecture uses Supabase to persist ingested mandi records, articles, and pipeline execution logs.

1. In your Supabase project dashboard, open the **SQL Editor**.
2. Create a new query and paste the contents of `supabase/migrations/202606060001_initial_schema.sql`.
3. Click **Run** to apply the schema.
4. *Alternatively, if you use the Supabase CLI, you can apply migrations locally or push them using:*
   ```bash
   supabase db push
   ```

---

## 5. Running the Pipeline

The pipeline is managed via `main.py`.

### 5.1 Local Development Sanity Check (Dev/Mock Mode)
To run a local run using mock CSV fixtures and SQLite (no external APIs or database required):
```bash
python main.py --mode dev
```

### 5.2 Production Live Run
To fetch live OGD data, pre-compute analytics, generate/translate articles using Gemini, and write the output to Supabase:
```bash
python main.py --mode live --date 2026-06-06
```

### 5.3 Live Demo Run (Single Market Focus)
To run in demo mode (which focuses on a single market like Sehore APMC and generates articles for verification):
```bash
python main.py --mode demo --date 2026-06-06
```

### 5.4 CLI Parameters

- `--date YYYY-MM-DD`: Target date for the pipeline execution. If not specified, defaults to the current date.
- `--mode [dev|live|demo|historical]`: Execution mode.
- `--commodities [soybean|cotton|all]`: Filter by specific commodity (defaults to `all`).
- `--skip-translate`: Skip the translation phase (English only).
- `--evaluate-only`: Skip ingestion and generation; run evaluation metrics on existing articles.

---

## 6. Running Tests

Unit and integration tests are powered by `pytest`. To run the test suite:
```bash
pytest
```

To run a specific test suite with verbose output:
```bash
pytest tests/test_ingestion.py -v
pytest tests/test_truthfulness.py -v
```

---

## 7. Troubleshooting Common Issues

### 7.1 OGD API Request Timeouts
The OGD India API (`api.data.gov.in`) can occasionally experience periods of latency. The pipeline handles this with connection and read timeouts (`OGD_CONNECT_TIMEOUT` and `OGD_READ_TIMEOUT`). If you encounter frequent timeout warnings:
- Increase `OGD_READ_TIMEOUT` in your `.env` (e.g., to `60` seconds).
- Ensure your `OGD_API_KEY` is active and correct.

### 7.2 Supabase Network Drops (`ConnectionResetError / ConnectionAborted`)
If you run the pipeline in an environment with unstable networks, calls to Supabase might occasionally reset. The database adapter (`supabase_backend.py`) includes a retry wrapper that automatically retries failed calls up to 4 times with exponential backoff.

### 7.3 Gemini Rate Limits / Service Unavailable (503)
The free tier of the Gemini API has rate limits (e.g., ~15 requests per minute). The LLM engine (`llm_engine.py`) has automatic rate limit backing-off and retries built in. If you see high-demand retry logs, the script will wait and retry automatically without crashing.
