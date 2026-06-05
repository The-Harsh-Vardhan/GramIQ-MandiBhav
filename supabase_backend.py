"""
supabase_backend.py -- Minimal PostgREST adapter for Supabase-backed storage.

Keeps the existing Python pipeline mostly unchanged by exposing explicit
functions for the current data access patterns used by the repo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

import config
from date_utils import normalize_date

logger = logging.getLogger("mandibhav.supabase")


class SupabaseBackendError(RuntimeError):
    """Raised when Supabase storage is requested but not configured correctly."""


def enabled() -> bool:
    return config.DATA_BACKEND == "supabase"


def configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY)


def require_configured() -> None:
    if not enabled():
        raise SupabaseBackendError("Supabase backend is not enabled.")
    if not configured():
        raise SupabaseBackendError(
            "DATA_BACKEND is 'supabase' but SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing."
        )


def _headers(prefer: Optional[str] = None) -> dict[str, str]:
    headers = {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _url(table: str) -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{table}"


def _request(
    method: str,
    table: str,
    *,
    params: Optional[dict[str, Any]] = None,
    payload: Optional[Any] = None,
    prefer: Optional[str] = None,
) -> Any:
    require_configured()
    response = requests.request(
        method=method,
        url=_url(table),
        headers=_headers(prefer),
        params=params,
        json=payload,
        timeout=config.SUPABASE_REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise SupabaseBackendError(
            f"Supabase {table} {method} failed: {response.status_code} {response.text}"
        )
    if not response.text:
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        return response.text


def insert_market_records(records: list, source: str = "mock") -> int:
    if not records:
        return 0
    payload = []
    for record in records:
        payload.append(
            {
                "commodity_slug": record.commodity.lower().strip(),
                "market_date": normalize_date(record.date),
                "state": record.state,
                "district": record.district,
                "market_name": record.market,
                "variety": record.variety,
                "grade": record.grade,
                "min_price": record.min_price,
                "max_price": record.max_price,
                "modal_price": record.modal_price,
                "arrival_tonnes": record.arrival_tonnes,
                "source": source,
            }
        )
    rows = _request(
        "POST",
        "market_data",
        params={"on_conflict": "commodity_slug,market_date,state,market_name,variety,grade"},
        payload=payload,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return len(rows or [])


def query_market_data(commodity: str, market_date: str) -> list[dict]:
    return _request(
        "GET",
        "market_data",
        params={
            "select": "*",
            "commodity_slug": f"eq.{commodity.lower()}",
            "market_date": f"eq.{normalize_date(market_date)}",
            "order": "state.asc,market_name.asc",
        },
    ) or []


def query_previous_day_data(commodity: str, market_date: str) -> list[dict]:
    previous_date = (
        datetime.fromisoformat(normalize_date(market_date)) - timedelta(days=1)
    ).date().isoformat()
    return query_market_data(commodity, previous_date)


def query_latest_available_date(commodity: str) -> Optional[str]:
    rows = _request(
        "GET",
        "market_data",
        params={
            "select": "market_date",
            "commodity_slug": f"eq.{commodity.lower()}",
            "order": "market_date.desc",
            "limit": "1",
        },
    ) or []
    if not rows:
        return None
    return rows[0].get("market_date")


def upsert_article(record: dict[str, Any]) -> dict[str, Any]:
    rows = _request(
        "POST",
        "articles",
        params={"on_conflict": "slug,language"},
        payload=record,
        prefer="resolution=merge-duplicates,return=representation",
    ) or []
    return rows[0] if rows else record


def query_articles_by_date(article_date: str, language: Optional[str] = "en") -> list[dict]:
    params = {
        "select": "*",
        "article_date": f"eq.{normalize_date(article_date)}",
        "order": "scope_key.asc",
    }
    if language:
        params["language"] = f"eq.{language}"
    return _request("GET", "articles", params=params) or []


def get_article(slug: str, language: str = "en") -> Optional[dict[str, Any]]:
    rows = _request(
        "GET",
        "articles",
        params={
            "select": "*",
            "slug": f"eq.{slug}",
            "language": f"eq.{language}",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None


def list_articles(
    *,
    language: str = "en",
    commodity_slug: Optional[str] = None,
    market_name: Optional[str] = None,
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "select": "*",
        "language": f"eq.{language}",
        "publish_status": "eq.published",
        "order": "article_date.desc,created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if commodity_slug:
        params["commodity_slug"] = f"eq.{commodity_slug}"
    if market_name:
        params["market_name"] = f"ilike.*{market_name}*"
    if start_date:
        params["article_date"] = f"gte.{normalize_date(start_date)}"
    if end_date:
        params["article_date"] = f"lte.{normalize_date(end_date)}"
    if query:
        params["or"] = (
            f"(title.ilike.*{query}*,meta_description.ilike.*{query}*,"
            f"body_html.ilike.*{query}*,market_name.ilike.*{query}*)"
        )
    return _request("GET", "articles", params=params) or []


def update_article(slug: str, fields: dict[str, Any], language: str = "en") -> Optional[dict[str, Any]]:
    rows = _request(
        "PATCH",
        "articles",
        params={
            "slug": f"eq.{slug}",
            "language": f"eq.{language}",
        },
        payload=fields,
        prefer="return=representation",
    ) or []
    return rows[0] if rows else None


def log_pipeline_run(run_id: str, run_date: str, mode: str) -> None:
    _request(
        "POST",
        "pipeline_runs",
        params={"on_conflict": "id"},
        payload={
            "id": run_id,
            "run_date": normalize_date(run_date),
            "mode": mode,
            "status": "running",
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )


def update_pipeline_run(run_id: str, metrics: dict[str, Any]) -> None:
    payload = {
        "status": metrics.get("status", "completed"),
        "records_processed": metrics.get("records_processed", 0),
        "articles_generated": metrics.get("articles_published", 0),
        "articles_review": metrics.get("articles_review", 0),
        "articles_blocked": metrics.get("articles_blocked", 0),
        "total_duration_seconds": metrics.get("total_duration_seconds", 0),
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }
    _request(
        "PATCH",
        "pipeline_runs",
        params={"id": f"eq.{run_id}"},
        payload=payload,
        prefer="return=minimal",
    )
