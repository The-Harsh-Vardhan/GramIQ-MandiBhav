"""
database.py — SQLite initialization, insert helpers, and query functions.

Uses Python's built-in sqlite3. No ORM. Simple and explicit.
Schema is created on first run (idempotent).
"""

import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
from datetime import date as date_type

from config import DB_PATH
from schemas import MarketRecord

logger = logging.getLogger("mandibhav.database")


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    """Yield a SQLite connection with WAL mode for safer concurrent reads."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commodity_slug TEXT NOT NULL,
            market_date TEXT NOT NULL,
            state TEXT NOT NULL,
            district TEXT DEFAULT '',
            market_name TEXT NOT NULL,
            variety TEXT DEFAULT '',
            grade TEXT DEFAULT '',
            min_price REAL NOT NULL DEFAULT 0,
            max_price REAL NOT NULL DEFAULT 0,
            modal_price REAL NOT NULL,
            arrival_tonnes REAL DEFAULT 0,
            source TEXT DEFAULT 'mock',
            ingested_at TEXT DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_unique
            ON market_data (commodity_slug, market_date, state, market_name, variety);

        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            commodity_slug TEXT NOT NULL,
            article_date TEXT NOT NULL,
            article_type TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            title TEXT NOT NULL,
            meta_description TEXT,
            body_html TEXT NOT NULL,
            keywords TEXT,
            json_ld TEXT,
            faq_json_ld TEXT,
            faqs TEXT,
            pre_computed_analytics TEXT,
            confidence_score REAL DEFAULT 0.0,
            publish_status TEXT DEFAULT 'draft',
            pipeline_run_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_article_unique
            ON articles (scope_key, article_date, language);

        CREATE INDEX IF NOT EXISTS idx_article_date
            ON articles (article_date DESC);

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            mode TEXT NOT NULL,
            articles_attempted INTEGER DEFAULT 0,
            articles_published INTEGER DEFAULT 0,
            articles_review INTEGER DEFAULT 0,
            articles_blocked INTEGER DEFAULT 0,
            total_duration_seconds REAL DEFAULT 0,
            status TEXT DEFAULT 'running',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        """)
    logger.info("Database initialized at: %s", DB_PATH)


# ---------------------------------------------------------------------------
# Market data operations
# ---------------------------------------------------------------------------

def insert_market_records(records: list[MarketRecord], source: str = "mock") -> int:
    """
    Insert market records. Checks for duplicates and records skipped records.
    Returns the count of newly inserted rows.
    """
    inserted = 0
    skipped_dupes = 0
    other_errors = 0

    sql_check = """
        SELECT 1 FROM market_data
        WHERE commodity_slug = ? AND market_date = ? AND state = ? AND market_name = ? AND variety = ?
        LIMIT 1
    """
    sql_insert = """
        INSERT INTO market_data
            (commodity_slug, market_date, state, district, market_name,
             variety, grade, min_price, max_price, modal_price, arrival_tonnes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    with get_connection() as conn:
        for r in records:
            comm = r.commodity.lower().strip()

            # Check for duplicate in database
            cursor = conn.execute(sql_check, (comm, r.date, r.state, r.market, r.variety))
            exists = cursor.fetchone()

            if exists:
                logger.info(
                    "Skipped record due to duplicate key: market=%s, commodity=%s, date=%s, state=%s, variety=%s",
                    r.market, comm, r.date, r.state, r.variety
                )
                skipped_dupes += 1
                continue

            # Perform insertion
            try:
                conn.execute(
                    sql_insert,
                    (
                        comm,
                        r.date,
                        r.state,
                        r.district,
                        r.market,
                        r.variety,
                        r.grade,
                        r.min_price,
                        r.max_price,
                        r.modal_price,
                        r.arrival_tonnes,
                        source,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError as ie:
                logger.warning(
                    "Skipped record due to constraint violation (market=%s, commodity=%s, date=%s): %s",
                    r.market, comm, r.date, ie
                )
                other_errors += 1
            except Exception as e:
                logger.error(
                    "Skipped record due to unexpected error/constraint violation (market=%s, commodity=%s, date=%s): %s",
                    r.market, comm, r.date, e
                )
                other_errors += 1

    logger.info(
        "Inserted %d / %d market records (source=%s). Skipped duplicates: %d. Other errors: %d.",
        inserted, len(records), source, skipped_dupes, other_errors
    )
    return inserted


def query_market_data(commodity: str, market_date: str) -> list[dict]:
    """Fetch all market records for a given commodity and date."""
    sql = """
        SELECT * FROM market_data
        WHERE commodity_slug = ? AND market_date = ?
        ORDER BY state, market_name
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (commodity.lower(), market_date)).fetchall()
    return [dict(row) for row in rows]


def query_previous_day_data(commodity: str, market_date: str) -> list[dict]:
    """
    Fetch market records for the day before market_date.
    Uses SQLite date arithmetic to find the previous date.
    """
    sql = """
        SELECT * FROM market_data
        WHERE commodity_slug = ?
          AND market_date = date(?, '-1 day')
        ORDER BY state, market_name
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (commodity.lower(), market_date)).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Article operations
# ---------------------------------------------------------------------------

def insert_article(article_data: dict) -> bool:
    """
    Insert a single article. Returns True if inserted, False if duplicate.
    article_data should match the articles table columns.
    """
    sql = """
        INSERT OR IGNORE INTO articles
            (id, commodity_slug, article_date, article_type, scope_key,
             language, title, meta_description, body_html, keywords,
             json_ld, faq_json_ld, faqs, pre_computed_analytics,
             confidence_score, publish_status, pipeline_run_id)
        VALUES
            (:id, :commodity_slug, :article_date, :article_type, :scope_key,
             :language, :title, :meta_description, :body_html, :keywords,
             :json_ld, :faq_json_ld, :faqs, :pre_computed_analytics,
             :confidence_score, :publish_status, :pipeline_run_id)
    """
    with get_connection() as conn:
        cursor = conn.execute(sql, article_data)
        return cursor.rowcount > 0


def query_articles_by_date(article_date: str, language: str = "en") -> list[dict]:
    """Fetch all articles for a given date and language."""
    sql = """
        SELECT * FROM articles
        WHERE article_date = ? AND language = ?
        ORDER BY article_type, scope_key
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (article_date, language)).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Pipeline run logging
# ---------------------------------------------------------------------------

def log_pipeline_run(run_id: str, run_date: str, mode: str) -> None:
    """Create a pipeline run record at the start of execution."""
    sql = """
        INSERT OR IGNORE INTO pipeline_runs (run_id, run_date, mode)
        VALUES (?, ?, ?)
    """
    with get_connection() as conn:
        conn.execute(sql, (run_id, run_date, mode))


def update_pipeline_run(run_id: str, metrics: dict) -> None:
    """Update a pipeline run record with final metrics."""
    sql = """
        UPDATE pipeline_runs
        SET articles_attempted = :articles_attempted,
            articles_published = :articles_published,
            articles_review = :articles_review,
            articles_blocked = :articles_blocked,
            total_duration_seconds = :total_duration_seconds,
            status = :status,
            completed_at = datetime('now')
        WHERE run_id = :run_id
    """
    metrics["run_id"] = run_id
    with get_connection() as conn:
        conn.execute(sql, metrics)
