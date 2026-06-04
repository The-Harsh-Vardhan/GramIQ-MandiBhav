"""
translator.py — Batched Gemini translation with QA checks.

One translation request can translate multiple scope articles into multiple languages.
"""

import json
import logging
import re
import time
from typing import Optional

from google.genai import types

from config import (
    GEMINI_MODEL, LLM_MAX_RETRIES, LLM_RETRY_DELAY_SECONDS, TRANSLATION_LANGUAGES,
    COMMODITY_TRANSLATIONS, VALID_TRANSLATION_LENGTH_RATIO,
)
from schemas import ArticleOutput, TranslatedArticle

logger = logging.getLogger("mandibhav.translator")

TRANSLATION_SYSTEM_PROMPT = (
    "Translate Indian mandi content faithfully. Preserve numbers, market names, HTML tags, "
    "and agricultural terms that should stay in English when instructed. Return JSON only."
)


def _extract_numbers(text: str) -> set[str]:
    """Extract all numeric values from text (handles ₹5,100 and 4.3% etc.)."""
    normalized = text.replace(",", "").replace("₹", "")
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", normalized))


def check_numeric_integrity(original_body: str, translated_body: str) -> bool:
    """Verify all numeric values from original appear in translation."""
    original_numbers = _extract_numbers(original_body)
    translated_numbers = _extract_numbers(translated_body)
    missing = original_numbers - translated_numbers
    if missing:
        logger.warning(
            "Translation numeric integrity FAILED. Missing: %s",
            ", ".join(sorted(missing)[:10])
        )
        return False
    return True


def check_length_ratio(original: str, translated: str) -> tuple[bool, float]:
    """Check if translation length is within acceptable ratio bounds."""
    if not original:
        return True, 1.0
    ratio = len(translated) / len(original)
    lo, hi = VALID_TRANSLATION_LENGTH_RATIO
    passed = lo <= ratio <= hi
    if not passed:
        logger.warning(
            "Translation length ratio %.2f outside acceptable range [%.2f, %.2f]",
            ratio, lo, hi
        )
    return passed, round(ratio, 3)


def _language_specs(codes: list[str], commodity: str) -> list[dict]:
    commodity_trans = COMMODITY_TRANSLATIONS.get(commodity, {})
    specs = []
    for code in codes:
        lang_info = TRANSLATION_LANGUAGES[code]
        specs.append({
            "code": code,
            "name": lang_info["name"],
            "script": lang_info["script"],
            "region": lang_info["region"],
            "commodity_name": commodity_trans.get(code, commodity.title()),
        })
    return specs


def _build_translation_prompt(
    commodity: str,
    articles: dict[str, ArticleOutput],
    missing_languages: dict[str, list[str]],
) -> str:
    payload = {
        "commodity": commodity,
        "rules": [
            "Keep all numbers unchanged.",
            "Keep HTML tags and structure unchanged except translated text nodes.",
            "Do not translate: MSP, APMC, quintal, mandi, GramIQ.",
            "Keep market and state names exactly as provided unless they already have a standard local form in the source text.",
        ],
        "output_schema": {
            "translations": [
                {
                    "scope_key": "string",
                    "language_code": "hi|mr|gu",
                    "title": "string",
                    "meta_description": "string",
                    "body_html": "string",
                }
            ]
        },
        "targets": [],
    }

    for scope_key, article in articles.items():
        payload["targets"].append({
            "scope_key": scope_key,
            "languages": _language_specs(missing_languages[scope_key], commodity),
            "title": article.title,
            "meta_description": article.meta_description,
            "body_html": article.body_html,
        })

    return json.dumps(payload, ensure_ascii=False)


def _translate_batch(prompt: str) -> Optional[str]:
    """Call Gemini API for translation and return raw JSON text."""
    from llm_engine import _get_client

    client = _get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=TRANSLATION_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=8192,
            ),
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        logger.error("Translation API call failed: %s", e)
        return None


def translate_articles(
    commodity: str,
    articles: dict[str, ArticleOutput],
    missing_languages: dict[str, list[str]],
) -> dict[str, dict[str, TranslatedArticle]]:
    """
    Translate multiple English articles into all requested languages in one Gemini call.
    Returns {scope_key: {language_code: TranslatedArticle}}.
    """
    if not articles:
        return {}

    prompt = _build_translation_prompt(commodity, articles, missing_languages)
    correction_suffix = ""

    for attempt in range(1, LLM_MAX_RETRIES + 2):
        raw = _translate_batch(prompt + correction_suffix)
        if raw:
            try:
                data = json.loads(raw)
                items = data.get("translations", [])
                translations: dict[str, dict[str, TranslatedArticle]] = {
                    scope_key: {} for scope_key in articles
                }
                for item in items:
                    scope_key = item["scope_key"]
                    lang_code = item["language_code"]
                    article = articles[scope_key]
                    numeric_ok = check_numeric_integrity(article.body_html, item["body_html"])
                    _, ratio = check_length_ratio(article.body_html, item["body_html"])
                    translations[scope_key][lang_code] = TranslatedArticle(
                        language_code=lang_code,
                        title=item["title"],
                        meta_description=item["meta_description"],
                        body_html=item["body_html"],
                        translation_provider="gemini",
                        numeric_integrity_passed=numeric_ok,
                        length_ratio=ratio,
                    )

                missing_pairs = []
                for scope_key, languages in missing_languages.items():
                    for lang_code in languages:
                        if lang_code not in translations.get(scope_key, {}):
                            missing_pairs.append(f"{scope_key}:{lang_code}")
                if missing_pairs:
                    raise ValueError(f"Missing translations: {missing_pairs}")

                logger.info(
                    "Translated %d %s article-language pairs in batch attempt %d",
                    sum(len(v) for v in translations.values()),
                    commodity,
                    attempt,
                )
                return translations
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Translation batch parse/validation failed: %s", e)
                correction_suffix = (
                    "\nReturn valid JSON only. Include one item for every requested scope_key and language_code."
                )

        if attempt <= LLM_MAX_RETRIES:
            logger.warning(
                "Translation attempt %d failed for %s. Retrying after %.1fs ...",
                attempt, commodity, LLM_RETRY_DELAY_SECONDS
            )
            time.sleep(LLM_RETRY_DELAY_SECONDS)

    logger.error("All translation attempts failed for commodity: %s", commodity)
    return {}
