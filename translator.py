"""
translator.py — Gemini-based multilingual translation with QA checks.

Uses the new google-genai SDK (google.genai).

Translates English ArticleOutput to Hindi, Marathi, and Gujarati.
Preserves HTML structure via explicit prompt instructions.
Runs automated QA checks on every translation.
"""

import re
import logging
import time
from typing import Optional

from google import genai
from google.genai import types

import config
from config import (
    GEMINI_MODEL, LLM_RETRY_DELAY_SECONDS, TRANSLATION_LANGUAGES,
    COMMODITY_TRANSLATIONS, VALID_TRANSLATION_LENGTH_RATIO,
    load_translation_prompt_template,
)
from schemas import ArticleOutput, TranslatedArticle

logger = logging.getLogger("mandibhav.translator")


# ---------------------------------------------------------------------------
# QA checks
# ---------------------------------------------------------------------------

def _extract_numbers(text: str) -> set[str]:
    """Extract all numeric values from text (handles ₹5,100 and 4.3% etc.)"""
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


# ---------------------------------------------------------------------------
# Prompt builder for translation
# ---------------------------------------------------------------------------

def build_translation_prompt(
    article: ArticleOutput,
    language_code: str,
    commodity: str,
) -> str:
    """Build the translation prompt for a target language."""
    lang_info = TRANSLATION_LANGUAGES.get(language_code, {})
    commodity_trans = COMMODITY_TRANSLATIONS.get(commodity, {})
    commodity_name_translated = commodity_trans.get(language_code, commodity.title())
    commodity_translations_str = f"{commodity.title()} = {commodity_name_translated}"

    template = load_translation_prompt_template()
    return template.format(
        target_language=lang_info.get("name", language_code),
        target_script=lang_info.get("script", ""),
        target_region=lang_info.get("region", "India"),
        commodity_translations=commodity_translations_str,
        article_body=article.body_html,
    )


# ---------------------------------------------------------------------------
# Single translation call
# ---------------------------------------------------------------------------

def _translate_text(client: genai.Client, prompt: str) -> Optional[str]:
    """Call Gemini API for translation and return translated text."""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=8192,
            ),
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        logger.error("Translation API call failed: %s", e)
        return None


def _translate_title_and_meta(
    client: genai.Client,
    title: str,
    meta_description: str,
    language_code: str,
    commodity: str,
) -> tuple[str, str]:
    """Translate the article title and meta description."""
    lang_info = TRANSLATION_LANGUAGES.get(language_code, {})
    lang_name = lang_info.get("name", language_code)
    commodity_trans = COMMODITY_TRANSLATIONS.get(commodity, {})
    commodity_name_translated = commodity_trans.get(language_code, commodity.title())

    prompt = f"""Translate the following from English to {lang_name}.

RULES:
- Keep all numbers unchanged
- Do NOT translate: MSP, APMC, quintal, mandi, GramIQ
- Keep market names (Mandsaur, Latur, Rajkot, etc.) as-is
- {commodity.title()} = {commodity_name_translated}
- Output ONLY the translations, separated by [META_SEP]

TITLE: {title}
META: {meta_description}

FORMAT YOUR RESPONSE AS:
[translated title][META_SEP][translated meta description]"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=512),
        )
        text = response.text.strip() if response.text else ""
        if "[META_SEP]" in text:
            parts = text.split("[META_SEP]", 1)
            return parts[0].strip(), parts[1].strip()
        return text, meta_description
    except Exception as e:
        logger.error("Title/meta translation failed: %s", e)
        return title, meta_description


# ---------------------------------------------------------------------------
# Main translation function
# ---------------------------------------------------------------------------

def translate_article(
    article: ArticleOutput,
    commodity: str,
) -> dict[str, TranslatedArticle]:
    """
    Translate one English ArticleOutput into all target languages.
    Returns dict of {language_code: TranslatedArticle}.
    """
    from llm_engine import _get_client
    client = _get_client()
    translations: dict[str, TranslatedArticle] = {}

    for lang_code in TRANSLATION_LANGUAGES:
        logger.info(
            "Translating → %s (%s) ...",
            lang_code, TRANSLATION_LANGUAGES[lang_code]["name"]
        )
        time.sleep(LLM_RETRY_DELAY_SECONDS)

        # Translate body HTML
        body_prompt = build_translation_prompt(article, lang_code, commodity)
        translated_body = _translate_text(client, body_prompt)

        if not translated_body:
            logger.warning("Body translation failed for lang=%s, skipping", lang_code)
            continue

        # Translate title and meta
        time.sleep(LLM_RETRY_DELAY_SECONDS * 0.5)
        translated_title, translated_meta = _translate_title_and_meta(
            client, article.title, article.meta_description, lang_code, commodity
        )

        # QA checks
        numeric_ok = check_numeric_integrity(article.body_html, translated_body)
        length_ok, ratio = check_length_ratio(article.body_html, translated_body)

        translations[lang_code] = TranslatedArticle(
            language_code=lang_code,
            title=translated_title,
            meta_description=translated_meta,
            body_html=translated_body,
            translation_provider="gemini",
            numeric_integrity_passed=numeric_ok,
            length_ratio=ratio,
        )

        qa_status = "✓" if (numeric_ok and length_ok) else "⚠"
        logger.info(
            "  %s %s | ratio=%.2f | numeric=%s",
            qa_status, lang_code, ratio, "OK" if numeric_ok else "WARN"
        )

    return translations
