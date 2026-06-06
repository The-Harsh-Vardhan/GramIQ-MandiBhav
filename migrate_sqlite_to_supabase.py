"""
migrate_sqlite_to_supabase.py -- One-time cutover utility for legacy SQLite data.

Reads the existing local SQLite database and upserts market data, articles, and
pipeline runs into Supabase using the same PostgREST adapter used by the live
pipeline.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import os
import sys
from pathlib import Path
from typing import Any

# Inject mandibhav package path for flat imports compatibility
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mandibhav"))

import config
import supabase_backend
from date_utils import normalize_date

logger = logging.getLogger("mandibhav.sqlite_migration")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate legacy SQLite records into Supabase."
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(config.DB_PATH),
        help="Path to the legacy SQLite database file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit per table for smoke tests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and transform records without sending them to Supabase.",
    )
    parser.add_argument(
        "--skip-market-data",
        action="store_true",
        help="Skip migrating normalized market_data rows.",
    )
    parser.add_argument(
        "--skip-articles",
        action="store_true",
        help="Skip migrating generated articles.",
    )
    parser.add_argument(
        "--skip-pipeline-runs",
        action="store_true",
        help="Skip migrating pipeline run telemetry.",
    )
    return parser.parse_args()


def open_sqlite(sqlite_path: str) -> sqlite3.Connection:
    path = Path(sqlite_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite file does not exist: {path}")
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def _json_or_default(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def slugify(value: str) -> str:
    parts = []
    for char in value.lower():
        if char.isalnum():
            parts.append(char)
        else:
            parts.append("-")
    slug = "".join(parts)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def sqlite_market_row_to_supabase(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "commodity_slug": row["commodity_slug"],
        "market_date": normalize_date(row["market_date"]),
        "state": row["state"],
        "district": row["district"] or "",
        "market_name": row["market_name"],
        "variety": row["variety"] or "",
        "grade": row["grade"] or "",
        "min_price": row["min_price"],
        "max_price": row["max_price"],
        "modal_price": row["modal_price"],
        "arrival_tonnes": row["arrival_tonnes"] or 0,
        "source": row["source"] or "ogd",
        "ingested_at": row["ingested_at"],
    }


def sqlite_article_row_to_supabase(row: sqlite3.Row) -> dict[str, Any]:
    analytics = _json_or_default(row["pre_computed_analytics"], {})
    scope_key = row["scope_key"]
    article_date = normalize_date(row["article_date"])
    language = row["language"] or "en"
    market_name = analytics.get("market") or analytics.get("scope_label") or scope_key
    state = analytics.get("state")
    slug = slugify(f"{row['commodity_slug']} {scope_key} {article_date}")

    return {
        "id": row["id"],
        "slug": slug,
        "title": row["title"],
        "article_date": article_date,
        "commodity_slug": row["commodity_slug"],
        "market_name": market_name,
        "state": state,
        "language": language,
        "body_html": row["body_html"],
        "meta_description": row["meta_description"] or "",
        "seo_title": row["title"],
        "credibility_score": row["confidence_score"] or 0,
        "data_source": analytics.get("data_source_status", "LIVE"),
        "report_type": analytics.get("report_type", "PRICE_SNAPSHOT"),
        "publish_status": row["publish_status"] or "draft",
        "scope_key": scope_key,
        "article_type": row["article_type"],
        "json_ld": _json_or_default(row["json_ld"], {}),
        "faq_json_ld": _json_or_default(row["faq_json_ld"], {}),
        "faqs": _json_or_default(row["faqs"], []),
        "keywords": _json_or_default(row["keywords"], []),
        "records_analyzed": analytics.get("record_count", 0),
        "contradictions_count": analytics.get("contradictions_count", 0),
        "unsupported_claims_count": analytics.get("unsupported_claims_count", 0),
        "scope_violations_count": analytics.get("scope_violations_count", 0),
        "truthfulness_score": analytics.get("truthfulness_score", 1.0),
        "data_source_disclosure_present": analytics.get("data_source_disclosure_present", True),
        "fallback_disclosure_present": analytics.get("fallback_disclosure_present", True),
        "unique_markets_count": analytics.get("unique_markets_count", 0),
        "unique_varieties_count": analytics.get("unique_varieties_count", 0),
        "unique_grades_count": analytics.get("unique_grades_count", 0),
        "pipeline_run_id": row["pipeline_run_id"],
        "created_at": row["created_at"],
        "ai_metadata": {
            "legacy_source": "sqlite",
            "observed_schema_version": 1,
        },
    }


def sqlite_run_row_to_supabase(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["run_id"],
        "run_date": normalize_date(row["run_date"]),
        "mode": row["mode"],
        "status": row["status"] or "completed",
        "records_processed": 0,
        "articles_generated": row["articles_published"] or 0,
        "articles_review": row["articles_review"] or 0,
        "articles_blocked": row["articles_blocked"] or 0,
        "total_duration_seconds": row["total_duration_seconds"] or 0,
        "created_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def fetch_rows(conn: sqlite3.Connection, table: str, limit: int | None = None) -> list[sqlite3.Row]:
    query = f"SELECT * FROM {table}"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def migrate_market_data(conn: sqlite3.Connection, dry_run: bool, limit: int | None) -> int:
    rows = fetch_rows(conn, "market_data", limit)
    payload = [sqlite_market_row_to_supabase(row) for row in rows]
    if dry_run or not payload:
        return len(payload)
    result = supabase_backend._request(
        "POST",
        "market_data",
        params={"on_conflict": "commodity_slug,market_date,state,market_name,variety,grade"},
        payload=payload,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return len(result or [])


def migrate_articles(conn: sqlite3.Connection, dry_run: bool, limit: int | None) -> int:
    rows = fetch_rows(conn, "articles", limit)
    payload = [sqlite_article_row_to_supabase(row) for row in rows]
    migrated = 0
    for item in payload:
        if not dry_run:
            supabase_backend.upsert_article(item)
        migrated += 1
    return migrated


def migrate_pipeline_runs(conn: sqlite3.Connection, dry_run: bool, limit: int | None) -> int:
    rows = fetch_rows(conn, "pipeline_runs", limit)
    payload = [sqlite_run_row_to_supabase(row) for row in rows]
    migrated = 0
    for item in payload:
        if not dry_run:
            supabase_backend._request(
                "POST",
                "pipeline_runs",
                params={"on_conflict": "id"},
                payload=item,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        migrated += 1
    return migrated


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if not args.dry_run:
        supabase_backend.require_configured()

    conn = open_sqlite(args.sqlite_path)
    try:
        summary: dict[str, int] = {}
        if not args.skip_market_data:
            summary["market_data"] = migrate_market_data(conn, args.dry_run, args.limit)
        if not args.skip_articles:
            summary["articles"] = migrate_articles(conn, args.dry_run, args.limit)
        if not args.skip_pipeline_runs:
            summary["pipeline_runs"] = migrate_pipeline_runs(conn, args.dry_run, args.limit)
    finally:
        conn.close()

    for table, count in summary.items():
        logger.info("%s: %d rows processed", table, count)


if __name__ == "__main__":
    main()
