"""
main.py — CLI entry point and pipeline orchestrator.

Usage:
    python main.py                           # Run for today in dev mode
    python main.py --date 2026-06-04         # Run for specific date
    python main.py --mode live               # Use live OGD API
    python main.py --commodities soybean     # Single commodity
    python main.py --skip-translate          # EN only (faster dev loop)
    python main.py --evaluate-only           # Re-evaluate existing output
    python main.py --help                    # Show all options

Pipeline flow:
    Init → Ingest → Analytics → Generate → Translate → Assemble → Evaluate
"""

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import date as date_cls
from pathlib import Path

logger = logging.getLogger("mandibhav.main")


def _find_cached_output(date: str, scope_key: str, language: str) -> Path | None:
    """Return the cached output JSON path for a scope/language if it exists."""
    import config

    candidates = [
        config.OUTPUT_DIR / date / scope_key / f"{language}.json",
        config.OUTPUT_DIR / date / "review" / f"{scope_key}_{language}.json",
        config.OUTPUT_DIR / date / "blocked" / f"{scope_key}_{language}.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_cached_article_output(
    cached_path: Path,
    payload,
    scope,
):
    """Rebuild an ArticleOutput-like object from the cached final JSON."""
    from schemas import ArticleOutput
    from seo_assembler import build_market_summary_table

    with open(cached_path, encoding="utf-8") as f:
        data = json.load(f)

    return ArticleOutput(
        title=data["title"],
        meta_description=data["meta_description"],
        body_html=data["body"],
        keywords=data["keywords"],
        market_summary_table=build_market_summary_table(payload),
        faqs=data["faqs"],
    ), data


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mandibhav",
        description="MandiBhav by GramIQ — Automated Multi-Lingual Mandi Rates Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                             # Dev mode, today's date
  python main.py --date 2026-06-04           # Specific date
  python main.py --mode live                 # Use OGD live API
  python main.py --skip-translate            # English only (faster)
  python main.py --evaluate-only             # Evaluate existing output
  python main.py --date 2026-06-04 --mode dev --commodities soybean
        """,
    )
    parser.add_argument(
        "--date",
        default=date_cls.today().isoformat(),
        help="Target date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--mode",
        choices=["dev", "live"],
        default=None,
        help="Pipeline mode: 'dev' uses CSV fixtures, 'live' uses OGD API (default: from PIPELINE_MODE env var)",
    )
    parser.add_argument(
        "--commodities",
        nargs="+",
        choices=["soybean", "cotton"],
        default=None,
        help="Commodities to process (default: all configured commodities)",
    )
    parser.add_argument(
        "--skip-translate",
        action="store_true",
        help="Skip translation — generate English articles only (faster)",
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Skip generation — only run the evaluation report on existing output",
    )
    parser.add_argument(
        "--skip-evaluate",
        action="store_true",
        help="Skip post-run evaluation report",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def stage_init(args: argparse.Namespace) -> tuple[str, str]:
    """Initialize configuration, database, and Gemini client."""
    # Override mode from CLI arg if provided
    if args.mode:
        import os
        os.environ["PIPELINE_MODE"] = args.mode

    import config
    from database import init_db
    from llm_engine import init_gemini

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 55)
    logger.info("MandiBhav by GramIQ Pipeline")
    logger.info("Date: %s | Mode: %s", args.date, config.PIPELINE_MODE)
    logger.info("=" * 55)

    # Initialize database
    init_db()

    # Initialize Gemini
    try:
        init_gemini()
    except ValueError as e:
        logger.error("Gemini initialization failed: %s", e)
        logger.error("Hint: Set GEMINI_API_KEY in your .env file.")
        sys.exit(1)

    run_id = str(uuid.uuid4())[:8]
    return run_id, config.PIPELINE_MODE


def stage_ingest(date: str, commodities: list[str]) -> None:
    """Ingest market data for all commodities into SQLite."""
    from ingestion import get_provider, ingest_commodity

    provider = get_provider()
    for commodity in commodities:
        ingest_commodity(date, commodity, provider)


def stage_analytics(date: str, knowledge: dict) -> tuple[dict, list]:
    """Compute analytics and build scope matrix."""
    from analytics import build_scope_matrix

    analytics_map, scope_targets = build_scope_matrix(date, knowledge)
    logger.info("Scope matrix: %d articles planned", len(scope_targets))
    return analytics_map, scope_targets


def stage_generate_and_assemble(
    date: str,
    run_id: str,
    analytics_map: dict,
    scope_targets: list,
    knowledge: dict,
    skip_translate: bool,
) -> tuple[int, int, int]:
    """Generate, translate, and write all articles. Returns (published, review, blocked)."""
    import config
    from llm_engine import generate_articles_for_commodity, build_keywords
    from translator import translate_articles
    from seo_assembler import compute_confidence, assemble_final_article, write_article_file
    from database import insert_article

    counts = {"published": 0, "review_required": 0, "blocked": 0}
    scopes_by_commodity: dict[str, list] = {}
    for scope in scope_targets:
        scopes_by_commodity.setdefault(scope.commodity, []).append(scope)

    for commodity, commodity_scopes in scopes_by_commodity.items():
        logger.info("Processing commodity batch: %s (%d scopes)", commodity, len(commodity_scopes))
        scope_lookup = {scope.scope_key: scope for scope in commodity_scopes}
        payload_lookup = {
            scope.scope_key: analytics_map[scope.scope_key]
            for scope in commodity_scopes
            if scope.scope_key in analytics_map
        }

        article_inputs: dict[str, object] = {}
        cached_meta: dict[str, dict] = {}
        missing_generation: dict[str, object] = {}

        for scope in commodity_scopes:
            payload = payload_lookup.get(scope.scope_key)
            if not payload:
                logger.warning("No analytics for scope: %s", scope.scope_key)
                counts["blocked"] += 1
                continue

            cached_en = _find_cached_output(date, scope.scope_key, "en")
            if cached_en:
                article_inputs[scope.scope_key], cached_meta[scope.scope_key] = _load_cached_article_output(
                    cached_en, payload, scope
                )
                logger.info("Cache hit: English article %s", scope.scope_key)
            else:
                missing_generation[scope.scope_key] = payload

        if missing_generation:
            generated = generate_articles_for_commodity(
                commodity, date, missing_generation, scope_lookup
            )
            article_inputs.update(generated)

        for scope_key, article in article_inputs.items():
            payload = payload_lookup[scope_key]
            scope = scope_lookup[scope_key]

            missing_langs: list[str] = []
            translations: dict[str, object] = {}
            if not skip_translate:
                for lang_code in config.TRANSLATION_LANGUAGES:
                    cached_tr = _find_cached_output(date, scope_key, lang_code)
                    if cached_tr:
                        logger.info("Cache hit: translation %s/%s", scope_key, lang_code)
                    else:
                        missing_langs.append(lang_code)

                if missing_langs:
                    batch_translations = translate_articles(
                        commodity,
                        {scope_key: article},
                        {scope_key: missing_langs},
                    )
                    translations = batch_translations.get(scope_key, {})

            if scope_key in cached_meta:
                confidence = cached_meta[scope_key]["confidence_score"]
                status = cached_meta[scope_key]["publish_status"]
                en_article = None
            else:
                keywords = build_keywords(payload.commodity, scope.article_type, scope)
                confidence, status = compute_confidence(article, payload, translations, keywords)
                en_article = assemble_final_article(
                    article, payload, scope, "en", confidence, status, run_id
                )
                write_article_file(en_article)

                try:
                    insert_article({
                        "id": f"{scope.scope_key}_{date}_en_{run_id}",
                        "commodity_slug": payload.commodity,
                        "article_date": date,
                        "article_type": scope.article_type,
                        "scope_key": scope.scope_key,
                        "language": "en",
                        "title": article.title,
                        "meta_description": article.meta_description,
                        "body_html": article.body_html,
                        "keywords": json.dumps(article.keywords),
                        "json_ld": json.dumps(en_article.json_ld),
                        "faq_json_ld": json.dumps(en_article.faq_json_ld),
                        "faqs": json.dumps(en_article.faqs),
                        "pre_computed_analytics": payload.model_dump_json(),
                        "confidence_score": confidence,
                        "publish_status": status,
                        "pipeline_run_id": run_id,
                    })
                except Exception as e:
                    logger.debug("DB insert failed (non-fatal): %s", e)

            counts[status] = counts.get(status, 0) + 1

            for lang_code, translated in translations.items():
                try:
                    tr_article = assemble_final_article(
                        article, payload, scope, lang_code, confidence, status, run_id, translated
                    )
                    write_article_file(tr_article)
                except Exception as e:
                    logger.warning("Write failed for %s/%s: %s", scope.scope_key, lang_code, e)

            if missing_generation:
                time.sleep(config.LLM_RETRY_DELAY_SECONDS)

    return counts.get("published", 0), counts.get("review_required", 0), counts.get("blocked", 0)


def stage_evaluate(date: str, pipeline_duration: float) -> None:
    """Run post-pipeline quality evaluation and print report."""
    from evaluate import generate_report, print_report, save_report_json

    report = generate_report(date)
    print_report(report, pipeline_time_seconds=pipeline_duration)
    save_report_json(report)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # Evaluate-only mode
    if args.evaluate_only:
        from evaluate import generate_report, print_report, save_report_json
        report = generate_report(args.date)
        print_report(report)
        save_report_json(report)
        return

    pipeline_start = time.time()

    # Stage 0: Init
    run_id, mode = stage_init(args)

    # Load knowledge layer (once, shared across all stages)
    import config
    knowledge = config.load_knowledge()
    logger.info("Knowledge loaded: %d domains", len(knowledge))

    # Determine commodities to process
    commodities = args.commodities or config.COMMODITIES
    logger.info("Commodities: %s", ", ".join(commodities))

    # Log pipeline run
    from database import log_pipeline_run
    log_pipeline_run(run_id, args.date, mode)

    # Stage 1: Ingest
    logger.info("--- Stage 1: Data Ingestion ---")
    stage_ingest(args.date, commodities)

    # Stage 2: Analytics
    logger.info("--- Stage 2: Analytics Pre-Computation ---")
    analytics_map, scope_targets = stage_analytics(args.date, knowledge)

    if not scope_targets:
        logger.error("No scope targets built — check if market data was ingested correctly.")
        sys.exit(1)

    # Stage 3: Generate + Translate + Assemble
    logger.info("--- Stage 3: Content Generation & Translation ---")
    logger.info("Generating %d articles ...", len(scope_targets))
    published, review, blocked = stage_generate_and_assemble(
        args.date, run_id, analytics_map, scope_targets, knowledge, args.skip_translate
    )

    pipeline_duration = time.time() - pipeline_start

    # Update pipeline run record
    from database import update_pipeline_run
    total_attempted = len(scope_targets)
    update_pipeline_run(run_id, {
        "articles_attempted": total_attempted,
        "articles_published": published,
        "articles_review": review,
        "articles_blocked": blocked,
        "total_duration_seconds": round(pipeline_duration, 2),
        "status": "completed",
    })

    # Stage 4: Evaluate
    if not args.skip_evaluate:
        logger.info("--- Stage 4: Quality Evaluation ---")
        stage_evaluate(args.date, pipeline_duration)

    mins = int(pipeline_duration // 60)
    secs = int(pipeline_duration % 60)
    logger.info("Pipeline complete in %dm %ds", mins, secs)


if __name__ == "__main__":
    main()
