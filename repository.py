"""
repository.py -- Article persistence abstraction for the pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import config
import supabase_backend
from schemas import AnalyticsPayload, FinalArticleJSON, ScopeTarget

logger = logging.getLogger("mandibhav.repository")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def build_article_slug(final_article: FinalArticleJSON) -> str:
    return slugify(f"{final_article.commodity} {final_article.scope_key} {final_article.date}")


def build_article_record(
    final_article: FinalArticleJSON,
    analytics: AnalyticsPayload,
    scope: ScopeTarget,
) -> dict:
    return {
        "id": f"{final_article.pipeline_run_id}:{final_article.language}:{final_article.scope_key}:{final_article.date}",
        "slug": build_article_slug(final_article),
        "title": final_article.title,
        "article_date": final_article.date,
        "commodity_slug": final_article.commodity,
        "market_name": scope.market or analytics.market or scope.scope_label,
        "state": scope.state or analytics.state,
        "language": final_article.language,
        "body_html": final_article.body,
        "meta_description": final_article.meta_description,
        "seo_title": final_article.seo_title or final_article.title,
        "credibility_score": final_article.credibility_score,
        "data_source": final_article.data_source_status,
        "report_type": final_article.report_type,
        "publish_status": final_article.publish_status,
        "scope_key": final_article.scope_key,
        "article_type": final_article.article_type,
        "json_ld": final_article.json_ld,
        "faq_json_ld": final_article.faq_json_ld,
        "faqs": final_article.faqs,
        "keywords": final_article.keywords,
        "records_analyzed": final_article.record_count,
        "contradictions_count": final_article.contradictions_count,
        "unsupported_claims_count": final_article.unsupported_claims_count,
        "scope_violations_count": final_article.scope_violations_count,
        "truthfulness_score": final_article.truthfulness_score,
        "data_source_disclosure_present": final_article.data_source_disclosure_present,
        "fallback_disclosure_present": final_article.fallback_disclosure_present,
        "unique_markets_count": final_article.unique_markets_count,
        "unique_varieties_count": final_article.unique_varieties_count,
        "unique_grades_count": final_article.unique_grades_count,
        "pipeline_run_id": final_article.pipeline_run_id,
    }


class ArticleRepository:
    """Simple repository facade used by the pipeline and future admin tooling."""

    def save_article(
        self,
        final_article: FinalArticleJSON,
        analytics: AnalyticsPayload,
        scope: ScopeTarget,
    ) -> dict:
        if not supabase_backend.enabled():
            logger.info(
                "Skipping canonical article upsert because DATA_BACKEND=%s",
                config.DATA_BACKEND,
            )
            return build_article_record(final_article, analytics, scope)
        record = build_article_record(final_article, analytics, scope)
        return supabase_backend.upsert_article(record)

    def get_article(self, slug: str, language: str = "en") -> Optional[dict]:
        if not supabase_backend.enabled():
            return None
        return supabase_backend.get_article(slug, language)

    def list_articles_by_date(self, article_date: str, language: Optional[str] = None) -> list[dict]:
        if supabase_backend.enabled():
            return supabase_backend.query_articles_by_date(article_date, language)
        from database import query_articles_by_date

        return query_articles_by_date(article_date, language)

    def list_articles(
        self,
        *,
        language: str = "en",
        commodity_slug: Optional[str] = None,
        market_name: Optional[str] = None,
        query: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        if not supabase_backend.enabled():
            return []
        return supabase_backend.list_articles(
            language=language,
            commodity_slug=commodity_slug,
            market_name=market_name,
            query=query,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    def update_article(self, slug: str, fields: dict, language: str = "en") -> Optional[dict]:
        if not supabase_backend.enabled():
            return None
        return supabase_backend.update_article(slug, fields, language)
