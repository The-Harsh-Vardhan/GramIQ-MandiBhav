"""
build_site.py — Static Site Generator for MandiBhav by GramIQ.

Reads article JSON files from output/{date}/ and produces a fully static
website in site/ — ready for GitHub Pages deployment.

Usage:
    python build_site.py                        # build from latest date
    python build_site.py --date 2026-06-04      # build specific date
    python build_site.py --output output/ --site-dir site/
    python build_site.py --base-url https://The-Harsh-Vardhan.github.io/GramIQ-MandiBhav

Workflow (10 steps):
    1.  Parse CLI args
    2.  Discover all published JSON files for target date
    3.  Load article registry into memory
    4.  Setup Jinja2 environment
    5.  Render article HTML pages  (one per article × language)
    6.  Render commodity index pages (EN + translated)
    7.  Render homepage (EN + language variants)
    8.  Generate sitemap.xml
    9.  Generate rss.xml
    10. Generate search.json
    11. Copy static assets
    12. Print build summary
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    OUTPUT_DIR, SITE_DIR, SITE_TEMPLATES_DIR, SITE_BASE_URL,
    SITE_TITLE, SITE_DESCRIPTION,
    ROOT_DIR,
)

logger = logging.getLogger("mandibhav.build_site")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LANGUAGES = {
    "en": {"label": "English",  "og_locale": "en_IN"},
    "hi": {"label": "हिंदी",    "og_locale": "hi_IN"},
    "mr": {"label": "मराठी",   "og_locale": "mr_IN"},
    "gu": {"label": "ગુજરાતી", "og_locale": "gu_IN"},
}

COMMODITY_META = {
    "soybean": {
        "name": "Soybean",
        "slug": "soybean",
        "description": (
            "Track daily soybean mandi prices across India's major markets — "
            "Madhya Pradesh, Maharashtra, Rajasthan and more. Updated daily from "
            "government APMC data with MSP comparison and seasonal analysis."
        ),
        "msp_year": "2025-26",
        "msp_value": 4892.0,
    },
    "cotton": {
        "name": "Cotton",
        "slug": "cotton",
        "description": (
            "Daily cotton mandi bhav from Gujarat, Maharashtra, Telangana and "
            "Andhra Pradesh. Includes F-1737, Shankar-6, and other varieties with "
            "government MSP benchmarks."
        ),
        "msp_year": "2025-26",
        "msp_value": 7121.0,
    },
}

ARTICLE_TYPE_LABELS = {
    "daily_commodity_report": "National Daily Report",
    "state_market_report":    "State Market Report",
    "market_spotlight":       "Market Spotlight",
    "best_market_today":      "Best Market Today",
    "top_gainers_losers":     "Top Gainers & Losers",
}

# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

LATEST_DATES = {}


def scope_to_slug(scope_key: str, commodity: str) -> str:
    """Convert scope_key to a URL-safe slug."""
    prefix = commodity + "_"
    slug = scope_key.removeprefix(prefix)
    return slug.replace("_", "-")


def article_url(article: dict, base_url: str = "") -> str:
    """Build the canonical URL for an article."""
    lang  = article.get("language", "en")
    comm  = article.get("commodity", "unknown")
    slug  = scope_to_slug(article.get("scope_key", "unknown"), comm)
    date_str = article.get("date", "")
    sk = article.get("scope_key", "unknown")
    
    is_latest = LATEST_DATES.get((sk, lang)) == date_str
    
    if is_latest:
        if lang == "en":
            return f"{base_url}/{comm}/{slug}/"
        return f"{base_url}/{lang}/{comm}/{slug}/"
    else:
        if lang == "en":
            return f"{base_url}/{comm}/{slug}/{date_str}/"
        return f"{base_url}/{lang}/{comm}/{slug}/{date_str}/"


def article_file_path(article: dict, site_dir: Path) -> Path:
    """Return the output file path for an article."""
    lang = article.get("language", "en")
    comm = article.get("commodity", "unknown")
    slug = scope_to_slug(article.get("scope_key", "unknown"), comm)
    date_str = article.get("date", "")
    if lang == "en":
        return site_dir / comm / slug / date_str / "index.html"
    return site_dir / lang / comm / slug / date_str / "index.html"


# ---------------------------------------------------------------------------
# Article discovery
# ---------------------------------------------------------------------------

def discover_articles(output_dir: Path, date: str) -> list[dict]:
    """Load all published (and review) article JSON files across all date directories."""
    date_dirs = []
    for item in output_dir.iterdir():
        if item.is_dir():
            match = re.match(r"^(\d{4}-\d{2}-\d{2})", item.name)
            if match:
                date_dirs.append(item)
                
    if not date_dirs:
        logger.error("No date directories found in %s", output_dir)
        return []

    articles: list[dict] = []
    for date_dir in date_dirs:
        for json_file in sorted(date_dir.rglob("*.json")):
            if json_file.name == "quality_report.json":
                continue
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                status = data.get("publish_status", "published")
                if status == "blocked":
                    continue
                articles.append(data)
            except Exception as e:
                logger.warning("Skipping %s: %s", json_file, e)

    logger.info("Discovered %d articles across all date directories", len(articles))
    return articles


def get_latest_date(output_dir: Path) -> str:
    """Return the most recent date directory name in output/."""
    dirs = [
        d.name for d in output_dir.iterdir()
        if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)
    ]
    if not dirs:
        return datetime.now().strftime("%Y-%m-%d")
    return sorted(dirs)[-1]


# ---------------------------------------------------------------------------
# Article registry
# ---------------------------------------------------------------------------

def build_registry(articles: list[dict]) -> dict:
    """
    Build an in-memory index of all articles.

    Returns:
    {
      "by_scope_lang": {(scope_key, lang): article},
      "by_commodity_lang": {(commodity, lang): [article, ...]},
      "by_commodity_type_lang": {(commodity, type, lang): [article, ...]},
      "en_articles": [article, ...],        # EN only
      "all_commodities": {"soybean", "cotton"},
    }
    """
    global LATEST_DATES
    LATEST_DATES.clear()
    
    reg: dict = {
        "by_scope_lang": {},
        "by_commodity_lang": {},
        "by_commodity_type_lang": {},
        "en_articles": [],
        "all_commodities": set(),
    }

    # Populate LATEST_DATES first
    for a in articles:
        sk   = a.get("scope_key", "")
        lang = a.get("language", "en")
        dt   = a.get("date", "")
        if not dt:
            continue
        key = (sk, lang)
        if key not in LATEST_DATES or dt > LATEST_DATES[key]:
            LATEST_DATES[key] = dt

    for a in articles:
        sk   = a.get("scope_key", "")
        lang = a.get("language", "en")
        comm = a.get("commodity", "")
        atype = a.get("article_type", "")
        dt   = a.get("date", "")

        key_sl = (sk, lang)
        # Only store the latest article in by_scope_lang
        if key_sl not in reg["by_scope_lang"] or dt > reg["by_scope_lang"][key_sl].get("date", ""):
            reg["by_scope_lang"][key_sl] = a

        key_cl = (comm, lang)
        reg["by_commodity_lang"].setdefault(key_cl, []).append(a)

        key_ctl = (comm, atype, lang)
        reg["by_commodity_type_lang"].setdefault(key_ctl, []).append(a)

        if lang == "en":
            reg["en_articles"].append(a)

        if comm:
            reg["all_commodities"].add(comm)

    return reg


# ---------------------------------------------------------------------------
# Jinja2 setup
# ---------------------------------------------------------------------------

def make_jinja_env(templates_dir: Path) -> Environment:
    """Create and configure the Jinja2 environment."""
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Custom filter: format date like "June 4, 2026"
    def format_date(iso_date: str) -> str:
        try:
            d = datetime.fromisoformat(iso_date)
            return d.strftime("%B %-d, %Y")
        except Exception:
            return iso_date

    # Windows-safe version (%-d not supported on Windows)
    def format_date_safe(iso_date: str) -> str:
        try:
            d = datetime.fromisoformat(iso_date)
            return d.strftime("%B %d, %Y").replace(" 0", " ")
        except Exception:
            return iso_date

    env.filters["format_date"] = format_date_safe
    return env


# ---------------------------------------------------------------------------
# Page context helpers
# ---------------------------------------------------------------------------

def base_context(base_url: str, current_lang: str = "en") -> dict:
    """Shared context variables injected into every page."""
    return {
        "base_url":     base_url,
        "current_lang": current_lang,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "site_title":   SITE_TITLE,
        "lang_urls":    {},   # overridden per-page
    }


def available_lang_links(scope_key: str, registry: dict, base_url: str) -> list[dict]:
    """Return language link list for an article's scope (relative paths, no base_url)."""
    links = []
    for code, info in LANGUAGES.items():
        article = registry["by_scope_lang"].get((scope_key, code))
        if article:
            links.append({
                "code":  code,
                "label": info["label"],
                "url":   article_url(article, ""),   # relative path only
            })
    return links


def lang_url_map(scope_key: str, registry: dict, base_url: str) -> dict:
    """Return {lang_code: url} for navbar language switcher."""
    return {
        code: article_url(a, base_url)
        for code in LANGUAGES
        if (a := registry["by_scope_lang"].get((scope_key, code)))
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_article_pages(articles: list[dict], registry: dict,
                          env: Environment, site_dir: Path, base_url: str) -> int:
    """Render one HTML page per article. Returns page count."""
    template = env.get_template("article.html")
    count = 0

    for article in articles:
        lang     = article.get("language", "en")
        comm     = article.get("commodity", "")
        scope_key = article.get("scope_key", "")
        atype    = article.get("article_type", "")

        scope_slug = scope_to_slug(scope_key, comm)
        canon_url  = f"{base_url}/{comm}/{scope_slug}/"

        # Build hreflang links
        hreflang = []
        for code, info in LANGUAGES.items():
            alt = registry["by_scope_lang"].get((scope_key, code))
            if alt:
                hreflang.append({"lang": code, "url": article_url(alt, base_url)})

        # Breadcrumbs for JSON-LD
        breadcrumbs = [
            {"label": "Home",           "url": "/"},
            {"label": comm.title(),     "url": f"/{comm}/"},
        ]
        if scope_slug != "national":
            breadcrumbs.append({"label": article.get("scope_key", scope_slug).replace("_", " ").title(),
                                 "url": f"/{comm}/{scope_slug}/"})

        ctx = {
            **base_context(base_url, lang),
            "page_title":       f"{article.get('title', '')} | {SITE_TITLE}",
            "meta_description": article.get("meta_description", ""),
            "og_title":         article.get("title", ""),
            "og_description":   article.get("meta_description", ""),
            "og_locale":        LANGUAGES[lang]["og_locale"],
            "canonical_url":    canon_url if lang == "en" else article_url(article, base_url),
            "hreflang_links":   hreflang,
            "breadcrumbs":      breadcrumbs,
            "keywords":         article.get("keywords", []),
            "json_ld_blocks":   [article.get("json_ld", {}), article.get("faq_json_ld", {})],
            "active_nav":       comm,
            "lang_urls":        lang_url_map(scope_key, registry, base_url),
            # Template-specific
            "article":          article,
            "type_label":       ARTICLE_TYPE_LABELS.get(atype, atype),
            "lang_label":       LANGUAGES[lang]["label"],
            "available_langs":  available_lang_links(scope_key, registry, base_url),
        }

        date_str = article.get("date", "")
        out_path = article_file_path(article, site_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(template.render(**ctx))
        count += 1

        # Write to the root/canonical path if it is the latest
        is_latest = LATEST_DATES.get((scope_key, lang)) == date_str
        if is_latest:
            if lang == "en":
                root_path = site_dir / comm / scope_slug / "index.html"
            else:
                root_path = site_dir / lang / comm / scope_slug / "index.html"
            root_path.parent.mkdir(parents=True, exist_ok=True)
            with open(root_path, "w", encoding="utf-8") as f:
                f.write(template.render(**ctx))
            logger.debug("Latest article written to root: %s", root_path.relative_to(site_dir))

    return count


def render_commodity_pages(registry: dict, env: Environment,
                            site_dir: Path, base_url: str, date: str) -> int:
    """Render one commodity index page per (commodity × language)."""
    template = env.get_template("commodity.html")
    count = 0

    for comm in sorted(registry["all_commodities"]):
        meta = COMMODITY_META.get(comm, {"name": comm.title(), "slug": comm,
                                         "description": "", "msp_year": "", "msp_value": None})

        for lang in LANGUAGES:
            articles_cl = registry["by_commodity_lang"].get((comm, lang), [])
            if not articles_cl:
                continue

            # Find the latest date for this commodity from the English articles
            comm_en_articles = registry["by_commodity_lang"].get((comm, "en"), [])
            latest_comm_date = max(a.get("date", "") for a in comm_en_articles) if comm_en_articles else date

            # Filter articles to only the latest date
            latest_articles_cl = [a for a in articles_cl if a.get("date") == latest_comm_date]

            # Group articles by type (only for the latest date)
            groups_dict: dict = {}
            for a in latest_articles_cl:
                atype = a.get("article_type", "other")
                groups_dict.setdefault(atype, []).append(a)

            article_groups = [
                {
                    "type_label": ARTICLE_TYPE_LABELS.get(t, t),
                    "articles": [
                        {
                            "title":            a.get("title", ""),
                            "url":              article_url(a, base_url),
                            "scope_label":      a.get("scope_key", "").replace(comm + "_", "").replace("_", " ").title(),
                            "date":             a.get("date", ""),
                            "confidence_score": a.get("confidence_score"),
                        }
                        for a in sorted(arts, key=lambda x: x.get("scope_key", ""))
                    ],
                }
                for t, arts in sorted(groups_dict.items())
            ]

            # Language variants for this commodity page (relative paths, no base_url)
            lang_variants = []
            for code, info in LANGUAGES.items():
                if registry["by_commodity_lang"].get((comm, code)):
                    if code == "en":
                        url = f"/{comm}/"
                    else:
                        url = f"/{code}/{comm}/"
                    lang_variants.append({"code": code, "label": info["label"], "url": url})

            canon_url = f"{base_url}/{comm}/" if lang == "en" else f"{base_url}/{lang}/{comm}/"

            # Find all unique dates for this commodity (sorted descending)
            unique_dates = sorted(list(set(a.get("date") for a in articles_cl if a.get("date"))), reverse=True)
            archive_list = []
            for d in unique_dates:
                # Find the primary report for this date
                date_articles = [a for a in articles_cl if a.get("date") == d]
                national_art = None
                for a in date_articles:
                    if a.get("article_type") == "daily_commodity_report" or "national" in a.get("scope_key", "") or "nagpur" in a.get("scope_key", ""):
                        national_art = a
                        break
                if not national_art and date_articles:
                    national_art = date_articles[0]
                if national_art:
                    archive_list.append({
                        "date": d,
                        "url": article_url(national_art, ""),
                    })

            ctx = {
                **base_context(base_url, lang),
                "page_title":       f"{meta['name']} Mandi Bhav Today | {SITE_TITLE}",
                "meta_description": meta["description"][:165],
                "canonical_url":    canon_url,
                "og_locale":        LANGUAGES[lang]["og_locale"],
                "active_nav":       comm,
                "lang_urls":        {code: (f"/{comm}/" if code == "en" else f"/{code}/{comm}/")
                                     for code in LANGUAGES
                                     if registry["by_commodity_lang"].get((comm, code))},
                # Template-specific
                "commodity":        meta,
                "article_groups":   article_groups,
                "total_articles":   len(latest_articles_cl),
                "latest_date":      latest_comm_date,
                "lang_label":       LANGUAGES[lang]["label"],
                "lang_variants":    lang_variants,
                "msp_info":         {"year": meta["msp_year"], "value": meta["msp_value"]},
                "current_lang":     lang,
                "archive_list":     archive_list,
            }

            if lang == "en":
                out_path = site_dir / comm / "index.html"
            else:
                out_path = site_dir / lang / comm / "index.html"

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(template.render(**ctx))
            count += 1

    return count


def render_homepage(registry: dict, env: Environment,
                    site_dir: Path, base_url: str, date: str) -> None:
    """Render the root index.html homepage."""
    template = env.get_template("homepage.html")

    en_articles = registry["en_articles"]
    latest_overall_date = max(a.get("date", "") for a in en_articles) if en_articles else date

    # Filter to only the latest date
    latest_en_articles = [a for a in en_articles if a.get("date") == latest_overall_date]
    recent_en = sorted(latest_en_articles, key=lambda a: a.get("scope_key", ""))[:6]
    recent = [
        {
            "title":      a.get("title", ""),
            "url":        article_url(a, base_url),
            "commodity":  a.get("commodity", ""),
            "type_label": ARTICLE_TYPE_LABELS.get(a.get("article_type", ""), ""),
            "date":       a.get("date", ""),
            "lang":       "en",
        }
        for a in recent_en
    ]

    commodities = []
    for comm, meta in COMMODITY_META.items():
        # Count only latest articles for the homepage view
        latest_comm_articles = [a for a in registry["by_commodity_lang"].get((comm, "en"), []) if a.get("date") == latest_overall_date]
        en_count = len(latest_comm_articles)
        if en_count == 0:
            continue
        lang_count = sum(
            1 for code in LANGUAGES
            if any(a.get("date") == latest_overall_date for a in registry["by_commodity_lang"].get((comm, code), []))
        )
        commodities.append({
            **meta,
            "article_count": en_count,
            "lang_count":    lang_count,
            "msp":           meta.get("msp_value"),
            "msp_year":      meta.get("msp_year", ""),
        })

    total_markets = max(
        (len({row.get("market") for a in latest_en_articles
               for row in a.get("market_summary_table", [])})),
        0,
    )

    # Archive list
    unique_dates = sorted(list(set(a.get("date") for a in en_articles if a.get("date"))), reverse=True)
    archive_list = []
    for d in unique_dates:
        date_articles = [a for a in en_articles if a.get("date") == d]
        national_art = None
        for a in date_articles:
            if a.get("article_type") == "daily_commodity_report" or "national" in a.get("scope_key", "") or "nagpur" in a.get("scope_key", ""):
                national_art = a
                break
        if not national_art and date_articles:
            national_art = date_articles[0]
        if national_art:
            archive_list.append({
                "date": d,
                "url": article_url(national_art, ""),
            })

    ctx = {
        **base_context(base_url, "en"),
        "page_title":       f"Mandi Bhav Today — Soybean & Cotton Prices | {SITE_TITLE}",
        "meta_description": SITE_DESCRIPTION,
        "og_title":         "MandiBhav by GramIQ — Daily Mandi Prices in 4 Languages",
        "og_description":   SITE_DESCRIPTION,
        "canonical_url":    f"{base_url}/",
        "active_nav":       "home",
        "json_ld_blocks":   [],
        # Template-specific
        "latest_date":      latest_overall_date,
        "commodities":      commodities,
        "recent_articles":  recent,
        "archive_list":     archive_list,
        "stats": {
            "total_articles": len(latest_en_articles),
            "total_markets":  total_markets,
        },
    }

    out_path = site_dir / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(template.render(**ctx))


# ---------------------------------------------------------------------------
# sitemap.xml
# ---------------------------------------------------------------------------

def generate_sitemap(registry: dict, base_url: str, date: str, site_dir: Path) -> None:
    """Generate sitemap.xml with all article and index page URLs."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
             '        xmlns:xhtml="http://www.w3.org/1999/xhtml">']

    def add_url(loc: str, lastmod: str, priority: str, changefreq: str = "daily") -> None:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(base_url + loc)}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")

    # Homepage
    add_url("/", date, "1.0")

    # Commodity index pages
    for comm in sorted(registry["all_commodities"]):
        add_url(f"/{comm}/", date, "0.9")

    # All article pages (EN canonical)
    for a in sorted(registry["en_articles"], key=lambda x: x.get("scope_key", "")):
        url = article_url(a, "")
        add_url(url, a.get("date", date), "0.8")

    # Translated article pages
    for (sk, lang), a in sorted(registry["by_scope_lang"].items()):
        if lang == "en":
            continue
        url = article_url(a, "")
        add_url(url, a.get("date", date), "0.6")

    lines.append("</urlset>")

    out = site_dir / "sitemap.xml"
    out.write_text("\n".join(lines), encoding="utf-8")
    url_count = sum(1 for l in lines if l.strip() == "<url>")
    logger.debug("Generated sitemap.xml with %d URLs", url_count)


# ---------------------------------------------------------------------------
# rss.xml
# ---------------------------------------------------------------------------

def generate_rss(registry: dict, base_url: str, date: str, site_dir: Path) -> None:
    """Generate RSS 2.0 feed for the latest English articles."""
    now_rfc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = []
    # Sort by date descending, then scope key ascending
    sorted_articles = sorted(
        registry["en_articles"],
        key=lambda x: (x.get("date", ""), x.get("scope_key", "")),
        reverse=True
    )
    for a in sorted_articles[:20]:
        url   = base_url + article_url(a, "")
        title = xml_escape(a.get("title", ""))
        desc  = xml_escape(a.get("meta_description", ""))
        pub   = a.get("date", date)
        comm  = a.get("commodity", "")
        items.append(f"""  <item>
    <title>{title}</title>
    <link>{xml_escape(url)}</link>
    <description>{desc}</description>
    <pubDate>{pub}</pubDate>
    <category>{comm.title()}</category>
    <guid isPermaLink="true">{xml_escape(url)}</guid>
  </item>""")

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{xml_escape(SITE_TITLE)}</title>
  <link>{xml_escape(base_url)}/</link>
  <description>{xml_escape(SITE_DESCRIPTION)}</description>
  <language>en-IN</language>
  <lastBuildDate>{now_rfc}</lastBuildDate>
  <atom:link href="{xml_escape(base_url)}/rss.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
</channel>
</rss>"""

    (site_dir / "rss.xml").write_text(feed, encoding="utf-8")
    logger.debug("Generated rss.xml with %d items", len(items))


# ---------------------------------------------------------------------------
# search.json
# ---------------------------------------------------------------------------

def generate_search_json(registry: dict, base_url: str, site_dir: Path) -> None:
    """Generate search.json index for client-side search."""
    index = []
    for a in registry["en_articles"] + [
        a for (sk, lang), a in registry["by_scope_lang"].items() if lang != "en"
    ]:
        # Extract a representative market/state from scope_key
        scope_key = a.get("scope_key", "")
        comm      = a.get("commodity", "")
        slug      = scope_to_slug(scope_key, comm)
        parts     = slug.split("-")
        state     = " ".join(p.title() for p in parts) if slug != "national" else ""

        index.append({
            "title":     a.get("title", ""),
            "commodity": comm,
            "language":  a.get("language", "en"),
            "type":      a.get("article_type", ""),
            "date":      a.get("date", ""),
            "url":       article_url(a, base_url),
            "state":     state,
            "scope":     scope_key,
        })

    (site_dir / "search.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.debug("Generated search.json with %d entries", len(index))


# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------

def copy_assets(site_dir: Path, templates_dir: Path) -> None:
    """Copy style.css, search.js to site/assets/."""
    assets_src = templates_dir / "assets"
    assets_dst = site_dir / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)

    for f in assets_src.iterdir():
        if f.is_file():
            shutil.copy2(f, assets_dst / f.name)
            logger.debug("Copied asset: %s", f.name)

    # Create a minimal favicon.ico if not present
    favicon = assets_dst / "favicon.ico"
    if not favicon.exists():
        # 16×16 transparent ICO (minimal valid binary)
        favicon.write_bytes(bytes([
            0,0,1,0,1,0,16,16,0,0,1,0,24,0,104,3,0,0,22,0,0,0
        ] + [0]*780))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MandiBhav Static Site Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to latest date in output/.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help=f"Article JSON output directory (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--site-dir",
        default=str(SITE_DIR),
        help=f"Site output directory (default: {SITE_DIR})",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL for absolute links (default: '' for relative URLs)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete site-dir before building",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


def sync_database_to_output(output_dir: Path) -> None:
    """Read all articles from the database and write them back to output/ if missing."""
    import sqlite3
    import json
    from database import DB_PATH
    
    if not DB_PATH.exists():
        logger.info("Database file not found at %s. Skipping DB-to-output sync.", DB_PATH)
        return
        
    logger.info("Syncing articles from database to output directory...")
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles")
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        logger.error("Failed to query articles from database: %s", e)
        return

    synced_count = 0
    for row in rows:
        try:
            r = dict(row)
            article_data = {
                "title": r["title"],
                "seo_title": r.get("title"),
                "meta_description": r["meta_description"],
                "body": r["body_html"],
                "keywords": json.loads(r["keywords"]) if r["keywords"] else [],
                "language": r["language"],
                "date": r["article_date"],
                "commodity": r["commodity_slug"],
                "article_type": r["article_type"],
                "scope_key": r["scope_key"],
                "json_ld": json.loads(r["json_ld"]) if r["json_ld"] else {},
                "faq_json_ld": json.loads(r["faq_json_ld"]) if r["faq_json_ld"] else {},
                "faqs": json.loads(r["faqs"]) if r["faqs"] else [],
                "confidence_score": r["confidence_score"],
                "publish_status": r["publish_status"],
                "pipeline_run_id": r["pipeline_run_id"],
                "generated_at": r.get("created_at", datetime.now().isoformat()),
                "credibility_score": r["confidence_score"],
                "data_source_status": "LIVE",
                "report_type": "PRICE_SNAPSHOT",
                "contradictions_count": 0,
                "unsupported_claims_count": 0,
                "scope_violations_count": 0,
                "truthfulness_score": 1.0,
                "fallback_disclosure_present": True,
                "data_source_disclosure_present": True,
                "unique_markets_count": 1,
                "unique_varieties_count": 0,
                "unique_grades_count": 0,
                "record_count": 0,
            }
            
            # Map pre-computed analytics if present
            if r["pre_computed_analytics"]:
                try:
                    analytics = json.loads(r["pre_computed_analytics"])
                    article_data["credibility_score"] = analytics.get("credibility_score", r["confidence_score"])
                    article_data["data_source_status"] = analytics.get("data_source_status", "LIVE")
                    article_data["report_type"] = analytics.get("report_type", "PRICE_SNAPSHOT")
                    article_data["contradictions_count"] = analytics.get("contradictions_count", 0)
                    article_data["unsupported_claims_count"] = analytics.get("unsupported_claims_count", 0)
                    article_data["scope_violations_count"] = analytics.get("scope_violations_count", 0)
                    article_data["truthfulness_score"] = analytics.get("truthfulness_score", 1.0)
                    article_data["fallback_disclosure_present"] = analytics.get("fallback_disclosure_present", True)
                    article_data["data_source_disclosure_present"] = analytics.get("data_source_disclosure_present", True)
                    article_data["unique_markets_count"] = analytics.get("unique_markets_count", 1)
                    article_data["unique_varieties_count"] = analytics.get("unique_varieties_count", 0)
                    article_data["unique_grades_count"] = analytics.get("unique_grades_count", 0)
                    article_data["record_count"] = analytics.get("record_count", 0)
                except Exception:
                    pass

            # Write to output folder
            date_str = r["article_date"]
            scope = r["scope_key"]
            lang = r["language"]
            status = r["publish_status"]
            
            if status == "published":
                file_dir = output_dir / date_str / scope
                file_path = file_dir / f"{lang}.json"
            elif status == "review_required":
                file_dir = output_dir / date_str / "review"
                file_path = file_dir / f"{scope}_{lang}.json"
            else:  # blocked
                file_dir = output_dir / date_str / "blocked"
                file_path = file_dir / f"{scope}_{lang}.json"
                
            # Only write if file doesn't exist to avoid unnecessary disk writes
            if not file_path.exists():
                file_dir.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(article_data, f, ensure_ascii=False, indent=2)
                synced_count += 1
        except Exception as e:
            logger.warning("Failed to sync database article: %s", e)
            
    if synced_count > 0:
        logger.info("Successfully synced %d articles from database to output folder.", synced_count)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    output_dir   = Path(args.output_dir)
    site_dir     = Path(args.site_dir)
    base_url     = args.base_url.rstrip("/")
    templates_dir = SITE_TEMPLATES_DIR

    # Sync database articles to output directory first
    try:
        sync_database_to_output(output_dir)
    except Exception as e:
        logger.warning("Database to output sync failed: %s", e)

    # Determine date
    if args.date:
        date = args.date
    else:
        date = get_latest_date(output_dir)
    logger.info("Building site for date: %s", date)

    # Step 1: Clean (optional)
    if args.clean and site_dir.exists():
        def remove_readonly(func, path, exc_info):
            import stat
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        try:
            shutil.rmtree(site_dir, onexc=remove_readonly)
        except TypeError:
            try:
                shutil.rmtree(site_dir, onerror=remove_readonly)
            except Exception as e:
                logger.warning("Could not fully clean site directory (some files may be locked): %s", e)
        except Exception as e:
            logger.warning("Could not fully clean site directory (some files may be locked): %s", e)
        logger.info("Cleaned site directory: %s", site_dir)

    # Step 2: Discover articles
    articles = discover_articles(output_dir, date)
    if not articles:
        logger.error("No articles found. Run main.py first.")
        sys.exit(1)

    # Step 3: Build registry
    registry = build_registry(articles)

    # Step 4: Setup Jinja2
    env = make_jinja_env(templates_dir)

    # Step 5: Render article pages
    n_articles = render_article_pages(articles, registry, env, site_dir, base_url)
    logger.info("Rendered %d article pages", n_articles)

    # Step 6: Render commodity index pages
    n_commodity = render_commodity_pages(registry, env, site_dir, base_url, date)
    logger.info("Rendered %d commodity pages", n_commodity)

    # Step 7: Render homepage
    render_homepage(registry, env, site_dir, base_url, date)
    logger.info("Rendered homepage")

    # Step 8: sitemap.xml
    generate_sitemap(registry, base_url, date, site_dir)

    # Step 9: rss.xml
    generate_rss(registry, base_url, date, site_dir)

    # Step 10: search.json
    generate_search_json(registry, base_url, site_dir)

    # Step 11: Static assets
    copy_assets(site_dir, templates_dir)

    # Step 12: Summary
    total_files = sum(1 for _ in site_dir.rglob("*") if _.is_file())
    summary = (
        f"\nBuild Complete!\n"
        f"  Date:          {date}\n"
        f"  Articles:      {n_articles} HTML pages\n"
        f"  Commodity idx: {n_commodity} pages\n"
        f"  Total files:   {total_files}\n"
        f"  Site output:   {site_dir}\n"
        f"  Base URL:      {base_url or '(relative)'}\n"
        f"\n"
        f"  Preview locally:\n"
        f"    python -m http.server 8080 --directory site/\n"
        f"  Then open: http://localhost:8080\n"
    )
    try:
        sys.stdout.buffer.write(summary.encode("utf-8"))
        sys.stdout.buffer.flush()
    except AttributeError:
        print(summary)


if __name__ == "__main__":
    main()
