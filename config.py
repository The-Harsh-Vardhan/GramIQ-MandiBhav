"""
config.py — Environment configuration, constants, and path management.

All settings are loaded from environment variables (with .env file support).
Import this module first in any other module.
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mandibhav.config")

# ---------------------------------------------------------------------------
# Load .env file if present (no external dependency required)
# ---------------------------------------------------------------------------
def _load_dotenv(env_path: Path = Path(".env")) -> None:
    """Manually load key=value pairs from a .env file into os.environ."""
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_dotenv()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
MOCK_DIR = DATA_DIR / "mock"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
FIXTURES_DIR = DATA_DIR / "fixtures"
TEMPLATES_DIR = ROOT_DIR / "templates"
PROMPTS_DIR = TEMPLATES_DIR / "prompts"
SEO_TEMPLATES_DIR = TEMPLATES_DIR / "seo"
OUTPUT_DIR = ROOT_DIR / "output"
DB_PATH = ROOT_DIR / "mandibhav.db"
SITE_DIR = ROOT_DIR / "site"
SITE_TEMPLATES_DIR = TEMPLATES_DIR / "site"

# ---------------------------------------------------------------------------
# Static site generation settings
# ---------------------------------------------------------------------------
# Set SITE_BASE_URL in .env for custom domains or subdirectory deployments.
# Examples:
#   SITE_BASE_URL=https://the-harsh-vardhan.github.io/GramIQ-MandiBhav
#   SITE_BASE_URL=https://mandibhav.gramiq.com
# Leave empty for relative URLs (works for local file:// browsing too).
SITE_BASE_URL: str = os.environ.get("SITE_BASE_URL", "").rstrip("/")
SITE_TITLE: str = "MandiBhav by GramIQ"
SITE_DESCRIPTION: str = (
    "Daily soybean and cotton mandi price reports in English, Hindi, "
    "Marathi and Gujarati — powered by government data and AI."
)


# ---------------------------------------------------------------------------
# Pipeline mode
# ---------------------------------------------------------------------------
PIPELINE_MODE: str = os.environ.get("PIPELINE_MODE", "dev")  # "dev" | "live" | "demo"
DEMO_MODE: bool = (os.environ.get("DEMO_MODE", "false").lower() == "true") or (PIPELINE_MODE == "demo")
DEBUG_OGD_SCHEMA: bool = os.environ.get("DEBUG_OGD_SCHEMA", "false").lower() == "true"
quota_exhausted_mode: bool = False

OGD_API_KEY: str = os.environ.get("OGD_API_KEY", "")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# OGD (data.gov.in) API endpoint for daily mandi prices
OGD_API_BASE_URL: str = "https://api.data.gov.in/resource"
OGD_RESOURCE_ID: str = os.environ.get(
    "OGD_RESOURCE_ID",
    "9ef84268-d588-465a-a308-a864a43d0070",
)
OGD_API_FORMAT: str = "json"
OGD_PAGE_LIMIT: int = int(os.environ.get("OGD_PAGE_LIMIT", "1000"))
OGD_COMMODITY_FILTERS: dict[str, list[str]] = {
    "soybean": ["Soyabean", "Soybean"],
    "cotton": ["Cotton"],
}
DEBUG_INGESTION: bool = os.environ.get("DEBUG_INGESTION", "false").lower() == "true"

# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
LLM_MAX_RETRIES: int = 2
LLM_RETRY_DELAY_SECONDS: float = 4.0   # Respect free-tier ~15 RPM

# ---------------------------------------------------------------------------
# Translation configuration
# ---------------------------------------------------------------------------
TRANSLATION_LANGUAGES: dict[str, dict[str, str]] = {
    "hi": {
        "name": "Hindi",
        "script": "Devanagari",
        "region": "Hindi-speaking states of India",
    },
    "mr": {
        "name": "Marathi",
        "script": "Devanagari",
        "region": "Maharashtra",
    },
    "gu": {
        "name": "Gujarati",
        "script": "Gujarati",
        "region": "Gujarat",
    },
}

# Commodity name translations for the translation prompt
COMMODITY_TRANSLATIONS: dict[str, dict[str, str]] = {
    "soybean": {"hi": "सोयाबीन", "mr": "सोयाबीन", "gu": "સોયાબીન"},
    "cotton":  {"hi": "कपास",   "mr": "कापूस",  "gu": "કપાસ"},
}

# ---------------------------------------------------------------------------
# Content configuration
# ---------------------------------------------------------------------------
COMMODITIES: list[str] = ["soybean", "cotton"]

# Minimum markets required per state to generate a state article
MIN_MARKETS_FOR_STATE_ARTICLE: int = 2

# Top N markets to feature in Market Spotlight articles
TOP_MARKETS_FOR_SPOTLIGHT: int = 2

# GramIQ Call-To-Action footer (appended to every article)
CTA_FOOTER_HTML: str = """
<div class="gramiq-cta">
  <hr/>
  <p><strong>📱 Get Real-Time Mandi Alerts on GramIQ</strong></p>
  <p>Download the <strong>GramIQ app</strong> for live mandi rates, 
  price alerts, and personalised market insights delivered directly 
  to your phone — in your language, at your fingertips.</p>
  <p><a href="https://gramiq.com/app" target="_blank" rel="noopener">
  ➤ Download GramIQ App</a></p>
</div>
"""

# ---------------------------------------------------------------------------
# SEO keyword templates
# ---------------------------------------------------------------------------
SEO_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "soybean": {
        "national": [
            "soybean mandi bhav today",
            "soybean price today India",
            "soyabean bhav",
            "soybean mandi rate",
        ],
        "state": [
            "soybean mandi bhav {state} today",
            "soybean bhav {state}",
            "soyabean rate {state}",
        ],
        "market": [
            "{market} mandi bhav today",
            "{market} soybean rate",
            "soybean mandi bhav {market}",
        ],
        "best_market": [
            "best mandi for soybean today",
            "highest soybean price today",
            "soybean mandi bhav today",
        ],
        "gainers_losers": [
            "soybean price up today",
            "soybean mandi bhav today",
            "soyabean bhav change today",
        ],
    },
    "cotton": {
        "national": [
            "cotton mandi bhav today",
            "kapas bhav today",
            "cotton price India today",
            "kapas rate today",
        ],
        "state": [
            "cotton mandi bhav {state} today",
            "kapas bhav {state}",
            "cotton rate {state}",
        ],
        "market": [
            "{market} mandi bhav today",
            "{market} cotton rate",
            "kapas bhav {market}",
        ],
        "best_market": [
            "best mandi for cotton today",
            "highest kapas price today",
            "cotton mandi bhav today",
        ],
        "gainers_losers": [
            "cotton price up today",
            "kapas bhav change today",
            "cotton mandi bhav today",
        ],
    },
}

# ---------------------------------------------------------------------------
# Confidence scoring thresholds
# ---------------------------------------------------------------------------
CONFIDENCE_AUTO_PUBLISH: float = 0.75
CONFIDENCE_REVIEW_REQUIRED: float = 0.40
PRICE_ANOMALY_THRESHOLD_PCT: float = 25.0  # Flag if day-over-day change > ±25%
MIN_WORD_COUNT: int = 200
MAX_WORD_COUNT: int = 1000
VALID_TRANSLATION_LENGTH_RATIO: tuple[float, float] = (0.65, 1.60)

# ---------------------------------------------------------------------------
# Knowledge loader
# ---------------------------------------------------------------------------
def load_knowledge() -> dict:
    """Load all 4 knowledge JSON files into a single dict. Called once at startup."""
    knowledge = {}
    files = {
        "msp":       KNOWLEDGE_DIR / "msp_rates.json",
        "commodity": KNOWLEDGE_DIR / "commodity_profiles.json",
        "market":    KNOWLEDGE_DIR / "market_profiles.json",
        "seasonal":  KNOWLEDGE_DIR / "seasonal_calendar.json",
    }
    for key, path in files.items():
        if path.exists():
            with open(path, encoding="utf-8") as f:
                knowledge[key] = json.load(f)
            logger.debug("Loaded knowledge file: %s", path.name)
        else:
            logger.warning("Knowledge file not found: %s", path)
            knowledge[key] = {}
    return knowledge


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------
def load_system_prompt() -> str:
    path = PROMPTS_DIR / "system_prompt.txt"
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_article_type_templates() -> dict:
    path = PROMPTS_DIR / "article_types.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_translation_prompt_template() -> str:
    path = PROMPTS_DIR / "translation_prompt.txt"
    with open(path, encoding="utf-8") as f:
        return f.read()
