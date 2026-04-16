"""Translation QA pass — detect suspect translations and retranslate them via Groq.

Runs *after* the primary translation (DeepL or Groq) to catch:
- Segments left in the source language (exact match)
- Very short segments whose punctuation-stripped text is identical source/target
- Long segments whose translation is suspiciously short (<45 % of source word count)

Suspects are retranslated individually via Groq LLM with ±3 surrounding segments
as context.  The QA pass is best-effort: if Groq is unavailable or rate-limited,
the original translation is kept untouched.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import TranslatedSubtitleSegment

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

LANGUAGE_NAMES = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
}

# How many neighbour segments to include as context when retranslating a suspect
_CONTEXT_WINDOW = 3
# Groq model — same as main translation provider
_MODEL = None  # resolved at call-time from settings

# Guard: skip QA if source == target lang (we can't detect it, but 0 suspects is fine)
_MIN_SUSPECT_RATIO = 0.0  # always run, even for 1 suspect
_MAX_QA_SEGMENTS = 60     # safety valve — skip QA if there are > N suspects (too many = systemic issue)
_QA_INTER_DELAY = 1.2     # seconds between Groq calls in the QA pass
_QA_RETRIES = 2


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text).lower().strip()


def _is_suspect(seg: TranslatedSubtitleSegment) -> bool:
    src = seg.source_text.strip()
    tgt = seg.translated_text.strip()

    if not src or not tgt:
        return False

    # Case 1: identical (not translated at all)
    if src.lower() == tgt.lower():
        return True

    src_words = src.split()
    tgt_words = tgt.split()

    # Case 2: short segment (≤ 3 words) — ignore punctuation differences
    if len(src_words) <= 3 and _strip_punct(src) == _strip_punct(tgt):
        return True

    # Case 3: long source but suspiciously short translation (likely truncated)
    if len(src_words) >= 7 and len(tgt_words) < len(src_words) * 0.45:
        return True

    return False


async def qa_retranslate(
    translated: list[TranslatedSubtitleSegment],
    target_language: str,
    source_language: str | None = None,
) -> list[TranslatedSubtitleSegment]:
    """Return a new list where suspect translations have been retranslated via Groq.

    The original list is never mutated.  If QA is skipped or fails completely,
    the input is returned as-is.
    """
    if not settings.groq_api_key:
        logger.debug("QA retranslation skipped: GROQ_API_KEY not configured")
        return translated

    suspect_indices = [i for i, seg in enumerate(translated) if _is_suspect(seg)]

    if not suspect_indices:
        logger.info("QA pass: no suspect translations found")
        return translated

    if len(suspect_indices) > _MAX_QA_SEGMENTS:
        logger.warning(
            f"QA pass: {len(suspect_indices)} suspect segments — too many to retranslate "
            f"individually (limit={_MAX_QA_SEGMENTS}). Skipping QA."
        )
        return translated

    logger.info(
        f"QA pass: {len(suspect_indices)}/{len(translated)} suspect segments — "
        f"retranslating via Groq with context..."
    )

    # Work on a mutable copy
    result = list(translated)
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)

    for call_idx, seg_idx in enumerate(suspect_indices):
        if call_idx > 0:
            await asyncio.sleep(_QA_INTER_DELAY)

        seg = translated[seg_idx]

        # Build context: ±_CONTEXT_WINDOW neighbours (already-translated text)
        ctx_start = max(0, seg_idx - _CONTEXT_WINDOW)
        ctx_end = min(len(translated), seg_idx + _CONTEXT_WINDOW + 1)
        context_segs = [
            translated[i] for i in range(ctx_start, ctx_end) if i != seg_idx
        ]
        context_text = "\n".join(
            f'[{s.start:.1f}s] "{s.translated_text}"' for s in context_segs
        )

        retranslated = await _retranslate_one(
            seg, lang_name, source_language, context_text
        )
        if retranslated is not None:
            result[seg_idx] = TranslatedSubtitleSegment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                source_text=seg.source_text,
                translated_text=retranslated,
                target_language=seg.target_language,
            )
            logger.debug(
                f"QA fixed seg {seg.id}: {seg.source_text!r} → {retranslated!r}"
            )

    fixed = sum(
        1
        for i, seg_idx in enumerate(suspect_indices)
        if result[seg_idx].translated_text != translated[seg_idx].translated_text
    )
    logger.info(f"QA pass complete: {fixed}/{len(suspect_indices)} segments improved")
    return result


async def _retranslate_one(
    seg: TranslatedSubtitleSegment,
    lang_name: str,
    source_language: str | None,
    context_text: str,
) -> str | None:
    """Retranslate a single segment with Groq.  Returns new text or None on failure."""
    model = settings.groq_translation_model

    source_hint = ""
    if source_language and source_language != "auto":
        src_name = LANGUAGE_NAMES.get(source_language, source_language)
        source_hint = f" The source language is {src_name}."

    context_block = (
        f"\n\nSurrounding translated lines (for context only — do NOT retranslate them):\n{context_text}"
        if context_text
        else ""
    )

    prompt = (
        f"Translate this single movie subtitle line to {lang_name}.{source_hint}\n"
        f"Return ONLY the translated text — no JSON, no explanation, no quotes.\n"
        f"Natural and idiomatic — write as a native {lang_name} speaker would say it.{context_block}\n\n"
        f"Line to translate: {seg.source_text}"
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional subtitle localizer. "
                    "You output only the translated subtitle line — nothing else."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    for attempt in range(_QA_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except (httpx.TransportError, httpx.TimeoutException) as e:
            logger.warning(f"QA retranslation network error: {e}")
            return None

        if response.status_code == 429:
            if attempt < _QA_RETRIES:
                wait = float(response.headers.get("retry-after", 10))
                logger.warning(f"QA 429 — waiting {wait:.0f}s")
                await asyncio.sleep(wait)
                continue
            logger.warning("QA retranslation rate-limited — keeping original")
            return None

        if response.status_code != 200:
            logger.warning(
                f"QA retranslation API error {response.status_code}: {response.text[:200]}"
            )
            return None

        body = response.json()
        text = body["choices"][0]["message"]["content"].strip()

        # Sanity check: if LLM echoed the source unchanged, discard
        if text.lower() == seg.source_text.lower():
            return None

        # Strip surrounding quotes the LLM sometimes adds
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1].strip()

        return text if text else None

    return None
