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
    if getattr(config, "DEMO_MODE", False):
        if scope_key == "soybean_nagpur":
            candidates.append(config.OUTPUT_DIR / "json" / "demo" / f"soybean_nagpur_latest_{language}.json")
    else:
        candidates.append(config.OUTPUT_DIR / "json" / "production" / f"article_{scope_key}_{language}.json")
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
        choices=["dev", "live", "demo"],
        default=None,
        help="Pipeline mode: 'dev' uses CSV fixtures, 'live' uses OGD API, 'demo' runs limited demo (default: from PIPELINE_MODE env var)",
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
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Force building static site and publishing to gh-pages branch",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Skip automatic building and publishing to gh-pages branch",
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
        if getattr(config, "quota_exhausted_mode", False):
            logger.warning("Short-circuiting stage_generate_and_assemble due to quota_exhausted_mode")
            break

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

            # Resolve data source status
            ingestion_source = getattr(config, "ingestion_data_source", "LIVE")
            if cached_en:
                ds_status = "LIVE_PLUS_CACHE" if ingestion_source == "LIVE" else "CACHE"
            else:
                ds_status = "LIVE" if ingestion_source == "LIVE" else "MOCK"
            payload.data_source_status = ds_status

            if cached_en:
                article_inputs[scope.scope_key], cached_meta[scope.scope_key] = _load_cached_article_output(
                    cached_en, payload, scope
                )
                logger.info("Cache hit: English article %s", scope.scope_key)
                if scope.scope_key == "soybean_nagpur":
                    config.demo_gen_status = "Cache Hit"
            else:
                missing_generation[scope.scope_key] = payload
                if scope.scope_key == "soybean_nagpur":
                    config.demo_gen_status = "Article Generated"

        if missing_generation:
            generated = generate_articles_for_commodity(
                commodity, date, missing_generation, scope_lookup
            )
            article_inputs.update(generated)
            for scope_key in set(missing_generation) - set(generated):
                logger.warning("Generation failed for: %s", scope_key)
                counts["blocked"] += 1

        translation_requests: dict[str, list[str]] = {}
        cached_translations: dict[str, dict[str, object]] = {}
        if not skip_translate:
            for scope_key in article_inputs:
                missing_langs: list[str] = []
                for lang_code in config.TRANSLATION_LANGUAGES:
                    cached_tr = _find_cached_output(date, scope_key, lang_code)
                    if cached_tr:
                        logger.info("Cache hit: translation %s/%s", scope_key, lang_code)
                        try:
                            with open(cached_tr, encoding="utf-8") as f:
                                tr_data = json.load(f)
                            from schemas import TranslatedArticle
                            translated = TranslatedArticle(
                                language_code=lang_code,
                                title=tr_data["title"],
                                meta_description=tr_data["meta_description"],
                                body_html=tr_data["body"],
                                translation_provider=tr_data.get("translation_provider", "gemini"),
                            )
                            cached_translations.setdefault(scope_key, {})[lang_code] = translated
                            if scope_key == "soybean_nagpur":
                                if lang_code == "hi":
                                    config.demo_trans_hi_ok = True
                                elif lang_code == "mr":
                                    config.demo_trans_mr_ok = True
                        except Exception as e:
                            logger.warning("Failed to load cached translation: %s", e)
                            missing_langs.append(lang_code)
                    else:
                        missing_langs.append(lang_code)
                if missing_langs:
                    translation_requests[scope_key] = missing_langs

        batched_translations = {}
        if translation_requests:
            batched_translations = translate_articles(
                commodity,
                {scope_key: article_inputs[scope_key] for scope_key in translation_requests},
                translation_requests,
            )

        for scope_key, article in article_inputs.items():
            payload = payload_lookup[scope_key]
            scope = scope_lookup[scope_key]
            translations = batched_translations.get(scope_key, {})
            if scope_key in cached_translations:
                translations.update(cached_translations[scope_key])

            if scope_key in cached_meta:
                confidence = cached_meta[scope_key]["confidence_score"]
                status = cached_meta[scope_key]["publish_status"]
                en_article = assemble_final_article(
                    article, payload, scope, "en", confidence, status, run_id
                )
                write_article_file(en_article)
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
                    if scope.scope_key == "soybean_nagpur":
                        if lang_code == "hi":
                            config.demo_trans_hi_ok = True
                        elif lang_code == "mr":
                            config.demo_trans_mr_ok = True
                except Exception as e:
                    logger.warning("Write failed for %s/%s: %s", scope.scope_key, lang_code, e)

        if missing_generation or translation_requests:
            time.sleep(config.LLM_RETRY_DELAY_SECONDS)

    return counts.get("published", 0), counts.get("review_required", 0), counts.get("blocked", 0)


def stage_evaluate(date: str, pipeline_duration: float) -> None:
    """Run post-pipeline quality evaluation and print report."""
    from evaluate import generate_report, print_report, save_report_json

    report = generate_report(date)
    print_report(report, pipeline_time_seconds=pipeline_duration)
    save_report_json(report)


def stage_publish(date: str, mode: str, force_publish: bool, skip_publish: bool) -> None:
    """Build the static site and publish it to the gh-pages branch on GitHub."""
    import config
    import os
    import subprocess
    import shutil
    import tempfile

    if skip_publish:
        logger.info("Publishing explicitly skipped via CLI flag.")
        config.demo_publish_ok = False
        return

    # Skip in GITHUB_ACTIONS since deployment is run by GITHUB_ACTIONS deploy job.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        logger.info("Running in GitHub Actions environment. Skipping automatic local Git push to gh-pages.")
        config.demo_publish_ok = True
        return

    should_publish = force_publish or (mode in ("live", "demo"))
    if not should_publish:
        logger.info("Publishing skipped (not in 'live' or 'demo' mode, and --publish was not specified).")
        config.demo_publish_ok = False
        return

    logger.info("--- Stage 5: Static Site Generation & Publishing ---")

    # 1. Run build_site.py
    logger.info("Building static site for date %s...", date)
    try:
        subprocess.run([sys.executable, "build_site.py", "--date", date, "--clean"], check=True)
    except Exception as e:
        logger.error("Failed to build static site: %s", e)
        return

    site_dir = config.SITE_DIR
    if not site_dir.exists():
        logger.error("Site directory %s does not exist. Cannot publish.", site_dir)
        return

    # 2. Get remote URL
    try:
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True
        ).strip()
    except Exception as e:
        logger.error("Failed to get Git remote origin URL: %s", e)
        return

    logger.info("Publishing to GitHub Pages (remote: %s, branch: gh-pages)...", remote_url)

    def run_git(cmd_args, cwd):
        res = subprocess.run(cmd_args, cwd=cwd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("Git command failed: %s", " ".join(cmd_args))
            if res.stdout:
                logger.error("Git stdout: %s", res.stdout)
            if res.stderr:
                logger.error("Git stderr: %s", res.stderr)
            raise subprocess.CalledProcessError(res.returncode, cmd_args, output=res.stdout, stderr=res.stderr)
        return res

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        try:
            # Initialize temp repository
            run_git(["git", "init"], cwd=tmpdir)
            run_git(["git", "config", "user.name", "GramIQ Publisher"], cwd=tmpdir)
            run_git(["git", "config", "user.email", "publisher@gramiq.com"], cwd=tmpdir)
            run_git(["git", "remote", "add", "origin", remote_url], cwd=tmpdir)
            
            # Fetch remote gh-pages branch
            fetch_res = subprocess.run(
                ["git", "fetch", "origin", "gh-pages"],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )
            if fetch_res.returncode == 0:
                run_git(["git", "checkout", "gh-pages"], cwd=tmpdir)
                # Clear all files except .git
                for item in tmp_path.iterdir():
                    if item.name == ".git":
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            else:
                run_git(["git", "checkout", "--orphan", "gh-pages"], cwd=tmpdir)

            # Copy built site files to temp repository
            shutil.copytree(site_dir, tmpdir, dirs_exist_ok=True)
            
            # Create .nojekyll
            (tmp_path / ".nojekyll").touch()

            # Commit and push
            run_git(["git", "add", "-A"], cwd=tmpdir)
            commit_msg = f"deploy: update site for latest run on {date}"
            # Check if there are changes to commit
            status_res = run_git(["git", "status", "--porcelain"], cwd=tmpdir)
            if not status_res.stdout.strip():
                logger.info("No changes to deploy. GitHub Pages is already up to date.")
                config.demo_publish_ok = True
                return

            run_git(["git", "commit", "-m", commit_msg], cwd=tmpdir)
            run_git(["git", "push", "origin", "gh-pages", "--force"], cwd=tmpdir)
            logger.info("Successfully published generated articles to GitHub Pages (gh-pages branch)!")
            config.demo_publish_ok = True
        except Exception as e:
            logger.error("Failed to push static site to gh-pages branch: %s", e)
            config.demo_publish_ok = False


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
    if mode == "demo":
        commodities = ["soybean"]
    logger.info("Commodities: %s", ", ".join(commodities))

    # Log pipeline run
    from database import log_pipeline_run
    log_pipeline_run(run_id, args.date, mode)

    # Stage 1: Ingest
    logger.info("--- Stage 1: Data Ingestion ---")
    stage_ingest(args.date, commodities)

    # Resolve Latest Available Date for demo mode after ingestion
    if mode == "demo":
        from database import query_latest_available_date
        latest_date = query_latest_available_date("soybean")
        if latest_date:
            logger.info("Demo Mode: Overriding target date from %s to latest available date %s", args.date, latest_date)
            args.date = latest_date

    # Stage 2: Analytics
    logger.info("--- Stage 2: Analytics Pre-Computation ---")
    analytics_map, scope_targets = stage_analytics(args.date, knowledge)
    config.analytics_payloads_cache = analytics_map

    if not scope_targets:
        logger.error("No scope targets built — check if market data was ingested correctly.")
        sys.exit(1)

    # Stage 3: Generate + Translate + Assemble
    logger.info("--- Stage 3: Content Generation & Translation ---")
    logger.info("Generating %d articles ...", len(scope_targets))

    # Auto-skip translation in demo mode unless explicitly forced
    skip_translate = args.skip_translate

    published, review, blocked = stage_generate_and_assemble(
        args.date, run_id, analytics_map, scope_targets, knowledge, skip_translate
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

    # Stage 5: Publish
    stage_publish(args.date, mode, args.publish, args.skip_publish)

    mins = int(pipeline_duration // 60)
    secs = int(pipeline_duration % 60)
    logger.info("Pipeline complete in %dm %ds", mins, secs)

    if mode == "demo":
        chosen_market = getattr(config, "demo_chosen_market", "Nagpur")
        ogd_records_count = getattr(config, "demo_records_count", 0)
        db_inserted = getattr(config, "db_inserted", 0)
        db_duplicates = getattr(config, "db_duplicates", 0)
        avg_price = getattr(config, "demo_avg_price", 0.0)
        gen_status = getattr(config, "demo_gen_status", "Article Generated")
        trans_hi = "✓" if getattr(config, "demo_trans_hi_ok", False) else "✗"
        trans_mr = "✓" if getattr(config, "demo_trans_mr_ok", False) else "✗"
        if args.skip_publish:
            pub_status = "SKIPPED"
        else:
            pub_status = "✓" if getattr(config, "demo_publish_ok", False) else "✗"

        # Get data source status for nagpur demo
        nagpur_payload = analytics_map.get("soybean_nagpur")
        ds_status = nagpur_payload.data_source_status if nagpur_payload else getattr(config, "ingestion_data_source", "LIVE")

        summary = f"""
OGD Fetch:
Commodity: Soybean
Market: {chosen_market}
Records: {ogd_records_count}

Database:
Inserted: {db_inserted}
Duplicates: {db_duplicates}

Analytics:
Average Price: ₹{avg_price}

Generation:
{gen_status}

Translation:
Hindi {trans_hi}
Marathi {trans_mr}

Publishing:
GitHub Pages {pub_status} (Data Source: {ds_status})
"""
        try:
            print(summary)
        except UnicodeEncodeError:
            safe_summary = summary.replace("₹", "Rs. ").replace("✓", "OK").replace("✗", "FAIL")
            print(safe_summary)


if __name__ == "__main__":
    main()
