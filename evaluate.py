"""
evaluate.py — Post-run quality metrics and evaluation report generator.

Scans all generated JSON files for a given date and computes:
- Content KPIs: factual accuracy, word count, CTA presence, diversity
- SEO KPIs: keyword in title, title length, meta length, JSON-LD validity, FAQ presence
- System KPIs: article count, success rate, confidence distribution

Prints a formatted quality report to stdout and optionally writes it to a JSON file.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config
from config import OUTPUT_DIR, MIN_WORD_COUNT, MAX_WORD_COUNT, CTA_FOOTER_HTML

logger = logging.getLogger("mandibhav.evaluate")

CTA_SIGNAL = "gramiq"  # The CTA is present if this string appears in body (case-insensitive)


# ---------------------------------------------------------------------------
# Data classes for evaluation results
# ---------------------------------------------------------------------------

@dataclass
class ArticleMetrics:
    file: str
    language: str
    scope_key: str
    article_type: str
    commodity: str
    confidence_score: float
    publish_status: str

    # Content
    word_count: int = 0
    word_count_ok: bool = False
    cta_present: bool = False
    faq_count: int = 0

    # SEO
    title_length: int = 0
    title_length_ok: bool = False
    meta_length: int = 0
    meta_length_ok: bool = False
    keyword_in_title: bool = False
    json_ld_valid: bool = False
    faq_json_ld_valid: bool = False
    h2_count: int = 0


@dataclass
class EvaluationReport:
    date: str
    total_files_scanned: int = 0
    articles_published: int = 0
    articles_review: int = 0
    articles_blocked: int = 0

    # Content
    avg_word_count: float = 0.0
    pct_word_count_ok: float = 0.0
    pct_cta_present: float = 0.0
    avg_faq_count: float = 0.0

    # SEO
    pct_title_ok: float = 0.0
    pct_meta_ok: float = 0.0
    pct_keyword_in_title: float = 0.0
    pct_json_ld_valid: float = 0.0
    pct_faq_json_ld_valid: float = 0.0
    pct_has_headings: float = 0.0

    # Confidence
    avg_confidence: float = 0.0
    min_confidence: float = 1.0
    max_confidence: float = 0.0

    article_metrics: list[ArticleMetrics] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-article metric computation
# ---------------------------------------------------------------------------

def _count_words(html: str) -> int:
    """Strip HTML tags and count words."""
    plain = re.sub(r"<[^>]+>", " ", html)
    return len(plain.split())


def _count_h2(html: str) -> int:
    """Count h2 tags in HTML body."""
    return len(re.findall(r"<h2[\s>]", html, re.IGNORECASE))


def _validate_json_ld(json_ld: dict, required_type: str) -> bool:
    """Check that a JSON-LD object has the required fields."""
    if not isinstance(json_ld, dict):
        return False
    if json_ld.get("@context") != "https://schema.org":
        return False
    if json_ld.get("@type") != required_type:
        return False
    return True


def _evaluate_article(file_path: Path) -> Optional[ArticleMetrics]:
    """Load and evaluate a single article JSON file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not read %s: %s", file_path, e)
        return None

    body = data.get("body", "")
    title = data.get("title", "")
    meta = data.get("meta_description", "")
    keywords = data.get("keywords", [])
    json_ld = data.get("json_ld", {})
    faq_json_ld = data.get("faq_json_ld", {})
    faqs = data.get("faqs", [])

    word_count = _count_words(body)
    title_len = len(title)
    meta_len = len(meta)
    h2_count = _count_h2(body)

    # Keyword in title: any keyword phrase appears in title
    keyword_in_title = any(kw.lower() in title.lower() for kw in keywords) if keywords else False

    return ArticleMetrics(
        file=str(file_path),
        language=data.get("language", "?"),
        scope_key=data.get("scope_key", "?"),
        article_type=data.get("article_type", "?"),
        commodity=data.get("commodity", "?"),
        confidence_score=data.get("confidence_score", 0.0),
        publish_status=data.get("publish_status", "?"),
        # Content
        word_count=word_count,
        word_count_ok=(MIN_WORD_COUNT <= word_count <= MAX_WORD_COUNT),
        cta_present=(CTA_SIGNAL in body.lower()),
        faq_count=len(faqs),
        # SEO
        title_length=title_len,
        title_length_ok=(50 <= title_len <= 120),
        meta_length=meta_len,
        meta_length_ok=(120 <= meta_len <= 165),
        keyword_in_title=keyword_in_title,
        json_ld_valid=_validate_json_ld(json_ld, "NewsArticle"),
        faq_json_ld_valid=_validate_json_ld(faq_json_ld, "FAQPage"),
        h2_count=h2_count,
    )


# ---------------------------------------------------------------------------
# Report aggregation
# ---------------------------------------------------------------------------

def _pct(count: int, total: int) -> float:
    return round(count / total * 100.0, 1) if total > 0 else 0.0


def generate_report(date: str, output_dir: Path = OUTPUT_DIR) -> EvaluationReport:
    """
    Scan all JSON article files under output/{date} and produce an EvaluationReport.
    """
    date_dir = output_dir / date
    report = EvaluationReport(date=date)

    if not date_dir.exists():
        report.errors.append(f"Output directory does not exist: {date_dir}")
        return report

    # Scan all JSON files (published + review)
    all_json_files = list(date_dir.rglob("*.json"))
    report.total_files_scanned = len(all_json_files)

    if not all_json_files:
        report.warnings.append("No JSON files found in output directory.")
        return report

    metrics_list: list[ArticleMetrics] = []
    for file_path in all_json_files:
        m = _evaluate_article(file_path)
        if m:
            metrics_list.append(m)

    if not metrics_list:
        return report

    n = len(metrics_list)
    report.article_metrics = metrics_list

    # Status distribution
    report.articles_published = sum(1 for m in metrics_list if m.publish_status == "published")
    report.articles_review = sum(1 for m in metrics_list if m.publish_status == "review_required")
    report.articles_blocked = sum(1 for m in metrics_list if m.publish_status == "blocked")

    # Content KPIs
    report.avg_word_count = round(sum(m.word_count for m in metrics_list) / n, 1)
    report.pct_word_count_ok = _pct(sum(1 for m in metrics_list if m.word_count_ok), n)
    report.pct_cta_present = _pct(sum(1 for m in metrics_list if m.cta_present), n)
    report.avg_faq_count = round(sum(m.faq_count for m in metrics_list) / n, 1)

    # SEO KPIs
    report.pct_title_ok = _pct(sum(1 for m in metrics_list if m.title_length_ok), n)
    report.pct_meta_ok = _pct(sum(1 for m in metrics_list if m.meta_length_ok), n)
    report.pct_keyword_in_title = _pct(sum(1 for m in metrics_list if m.keyword_in_title), n)
    report.pct_json_ld_valid = _pct(sum(1 for m in metrics_list if m.json_ld_valid), n)
    report.pct_faq_json_ld_valid = _pct(sum(1 for m in metrics_list if m.faq_json_ld_valid), n)
    report.pct_has_headings = _pct(sum(1 for m in metrics_list if m.h2_count > 0), n)

    # Confidence
    scores = [m.confidence_score for m in metrics_list]
    report.avg_confidence = round(sum(scores) / n, 3)
    report.min_confidence = round(min(scores), 3)
    report.max_confidence = round(max(scores), 3)

    # Warnings for low performers
    for m in metrics_list:
        if not m.word_count_ok:
            report.warnings.append(f"{m.scope_key} ({m.language}): word count {m.word_count} out of range")
        if not m.json_ld_valid:
            report.warnings.append(f"{m.scope_key} ({m.language}): NewsArticle JSON-LD invalid")
        if not m.cta_present:
            report.warnings.append(f"{m.scope_key} ({m.language}): GramIQ CTA missing")
        if m.confidence_score < 0.40:
            report.warnings.append(f"{m.scope_key} ({m.language}): low confidence {m.confidence_score:.3f}")

    return report


# ---------------------------------------------------------------------------
# Formatted report output
# ---------------------------------------------------------------------------

def print_report(report: EvaluationReport, pipeline_time_seconds: float = 0.0) -> None:
    """Print a formatted quality report to stdout."""
    mins = int(pipeline_time_seconds // 60)
    secs = int(pipeline_time_seconds % 60)
    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

    pub = report.articles_published
    rev = report.articles_review
    blk = report.articles_blocked
    total = report.total_files_scanned

    lines = [
        "",
        "═" * 55,
        f"  MandiBhav Quality Report — {report.date}",
        "═" * 55,
        "",
        "  PIPELINE",
        f"  ├── Total files:              {total}",
        f"  ├── Published (≥0.75):        {pub}  {'✅' if pub == total else '⚠️'}",
        f"  ├── Review Required (0.40-0.74): {rev}",
        f"  ├── Blocked (<0.40):          {blk}",
        f"  └── Pipeline time:            {time_str}",
        "",
        "  CONTENT",
        f"  ├── Avg word count:           {report.avg_word_count} words",
        f"  ├── Word count OK:            {report.pct_word_count_ok}%  {'✅' if report.pct_word_count_ok >= 90 else '⚠️'}",
        f"  ├── CTA present:              {report.pct_cta_present}%  {'✅' if report.pct_cta_present == 100 else '❌'}",
        f"  └── Avg FAQs per article:     {report.avg_faq_count}",
        "",
        "  SEO",
        f"  ├── Keyword in title:         {report.pct_keyword_in_title}%  {'✅' if report.pct_keyword_in_title >= 95 else '⚠️'}",
        f"  ├── Title length OK:          {report.pct_title_ok}%  {'✅' if report.pct_title_ok >= 90 else '⚠️'}",
        f"  ├── Meta desc length OK:      {report.pct_meta_ok}%  {'✅' if report.pct_meta_ok >= 90 else '⚠️'}",
        f"  ├── Has H2 headings:          {report.pct_has_headings}%  {'✅' if report.pct_has_headings >= 95 else '⚠️'}",
        f"  ├── JSON-LD NewsArticle OK:   {report.pct_json_ld_valid}%  {'✅' if report.pct_json_ld_valid == 100 else '❌'}",
        f"  └── JSON-LD FAQPage OK:       {report.pct_faq_json_ld_valid}%  {'✅' if report.pct_faq_json_ld_valid == 100 else '❌'}",
        "",
        "  CONFIDENCE",
        f"  ├── Average:                  {report.avg_confidence:.3f}",
        f"  ├── Minimum:                  {report.min_confidence:.3f}",
        f"  └── Maximum:                  {report.max_confidence:.3f}",
        "",
    ]

    if report.warnings:
        lines.append(f"  WARNINGS ({len(report.warnings)})")
        for w in report.warnings[:10]:
            lines.append(f"  ⚠️  {w}")
        if len(report.warnings) > 10:
            lines.append(f"  ... and {len(report.warnings) - 10} more")
        lines.append("")

    if report.errors:
        lines.append(f"  ERRORS ({len(report.errors)})")
        for e in report.errors:
            lines.append(f"  ❌  {e}")
        lines.append("")

    lines.append(f"  OUTPUT: output/{report.date}/")
    lines.append("═" * 55)
    lines.append("")

    print("\n".join(lines))


def save_report_json(report: EvaluationReport, output_dir: Path = OUTPUT_DIR) -> Path:
    """Save the evaluation report as a JSON file."""
    report_dir = output_dir / report.date
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "quality_report.json"

    # Serialize, excluding the full article_metrics list (too verbose for the main report)
    summary = {
        "date": report.date,
        "total_files": report.total_files_scanned,
        "articles_published": report.articles_published,
        "articles_review": report.articles_review,
        "articles_blocked": report.articles_blocked,
        "content": {
            "avg_word_count": report.avg_word_count,
            "pct_word_count_ok": report.pct_word_count_ok,
            "pct_cta_present": report.pct_cta_present,
            "avg_faq_count": report.avg_faq_count,
        },
        "seo": {
            "pct_keyword_in_title": report.pct_keyword_in_title,
            "pct_title_ok": report.pct_title_ok,
            "pct_meta_ok": report.pct_meta_ok,
            "pct_has_headings": report.pct_has_headings,
            "pct_json_ld_valid": report.pct_json_ld_valid,
            "pct_faq_json_ld_valid": report.pct_faq_json_ld_valid,
        },
        "confidence": {
            "average": report.avg_confidence,
            "min": report.min_confidence,
            "max": report.max_confidence,
        },
        "warnings": report.warnings,
        "errors": report.errors,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("Quality report saved: %s", report_path)
    return report_path
