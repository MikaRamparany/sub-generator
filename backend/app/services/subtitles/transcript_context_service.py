"""Transcript-level context analysis for improved translation quality.

Performs a SINGLE Groq LLM call per job to extract structured context from
the full source transcript.  The result is injected into both the translation
phase and the QA pass to improve consistency of proper nouns, recurring terms,
and ambiguous words.

Cost: ~1 LLM call (~800–1500 tokens) per job, only in premium mode.
Never invents external knowledge — infers only from the transcript itself.
"""
from __future__ import annotations

import json
import re

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.context import GlossaryEntry, TranscriptContext
from app.models.schemas import SubtitleSegment

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Max segments to include in the analysis prompt.
# If the transcript is longer, we sample evenly to stay within token budget.
_MAX_ANALYSIS_LINES = 150
# Max chars per line in the compressed transcript sent to the LLM
_MAX_LINE_CHARS = 80


def _compress_transcript(segments: list[SubtitleSegment]) -> str:
    """Return a compact representation of the transcript for the LLM.

    If there are more than _MAX_ANALYSIS_LINES segments, sample evenly so we
    cover the whole film rather than just the opening.
    """
    if not segments:
        return ""

    if len(segments) <= _MAX_ANALYSIS_LINES:
        selected = segments
    else:
        step = len(segments) / _MAX_ANALYSIS_LINES
        selected = [segments[int(i * step)] for i in range(_MAX_ANALYSIS_LINES)]

    lines = []
    for seg in selected:
        text = seg.text.replace("\n", " ").strip()
        if len(text) > _MAX_LINE_CHARS:
            text = text[:_MAX_LINE_CHARS] + "…"
        lines.append(text)

    return "\n".join(lines)


async def analyze_transcript(
    segments: list[SubtitleSegment],
    source_language: str | None,
    target_language: str,
) -> TranscriptContext | None:
    """Analyse the full transcript and return structured context.

    Returns None if:
    - GROQ_API_KEY is not configured
    - The transcript is too short to be informative (< 20 segments)
    - The LLM call fails (best-effort, never blocks the pipeline)
    """
    if not settings.groq_api_key:
        logger.debug("Transcript analysis skipped: GROQ_API_KEY not configured")
        return None

    if len(segments) < 20:
        logger.debug("Transcript analysis skipped: too few segments")
        return None

    compressed = _compress_transcript(segments)
    if not compressed:
        return None

    src_hint = f" The source language is {source_language}." if source_language else ""
    tgt_name = _LANGUAGE_NAMES.get(target_language, target_language)

    prompt = (
        f"Analyse the following movie/series subtitle transcript.{src_hint}\n"
        f"We will translate it to {tgt_name}.\n\n"
        f"Your task: infer structured context FROM THIS TRANSCRIPT ONLY.\n"
        f"Do NOT invent external knowledge. If uncertain, use low confidence.\n\n"
        f"Return a single JSON object with these fields:\n"
        f"- proper_nouns: list of character names, place names, brand names "
        f"that should remain untranslated (e.g. ['Zoe', 'Marcus', 'Apex'])\n"
        f"- glossary: list of objects {{\"src\": \"...\", \"preferred\": \"...\", \"note\": \"...\"}} "
        f"for recurring terms that need consistent translation "
        f"(e.g. {{\"src\": \"Fire\", \"preferred\": \"Feu\", \"note\": \"military command\"}})\n"
        f"- ambiguous_words: list of source words that are context-sensitive "
        f"and could be mistranslated without context (e.g. ['Fire', 'Clear', 'Mark'])\n"
        f"- style: short description of genre/register "
        f"(e.g. 'military action thriller, terse dialogue')\n"
        f"- confidence: float 0–1 (1.0 = high confidence in your analysis)\n\n"
        f"Rules:\n"
        f"- Only include terms you can identify with reasonable certainty\n"
        f"- If a term appears fewer than 3 times, skip it unless it is clearly important\n"
        f"- Glossary preferred translations must be in {tgt_name}\n"
        f"- Return ONLY the JSON object, no markdown, no explanation\n\n"
        f"TRANSCRIPT:\n{compressed}"
    )

    payload = {
        "model": settings.groq_translation_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional subtitle analyst. "
                    "You extract structured context from transcripts to improve translation quality. "
                    "You output only valid JSON — no markdown, no explanation."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except (httpx.TransportError, httpx.TimeoutException) as e:
        logger.warning(f"Transcript analysis network error: {e} — skipping")
        return None

    if response.status_code == 429:
        logger.warning("Transcript analysis rate-limited — skipping (non-blocking)")
        return None

    if response.status_code != 200:
        logger.warning(
            f"Transcript analysis API error {response.status_code}: "
            f"{response.text[:200]} — skipping"
        )
        return None

    raw = response.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Transcript analysis: invalid JSON from LLM ({e}) — skipping")
        return None

    if not isinstance(data, dict):
        logger.warning("Transcript analysis: expected JSON object — skipping")
        return None

    proper_nouns = [str(x) for x in data.get("proper_nouns", []) if isinstance(x, str)]
    ambiguous = [str(x) for x in data.get("ambiguous_words", []) if isinstance(x, str)]
    style = str(data.get("style", ""))
    confidence = float(data.get("confidence", 0.8))

    glossary: list[GlossaryEntry] = []
    for item in data.get("glossary", []):
        if isinstance(item, dict) and "src" in item and "preferred" in item:
            glossary.append(GlossaryEntry(
                src=str(item["src"]),
                preferred=str(item["preferred"]),
                note=str(item.get("note", "")),
            ))

    ctx = TranscriptContext(
        proper_nouns=proper_nouns,
        glossary=glossary,
        ambiguous_words=ambiguous,
        style=style,
        confidence=confidence,
    )

    logger.info(
        f"Transcript analysis complete: {len(proper_nouns)} proper nouns, "
        f"{len(glossary)} glossary entries, "
        f"{len(ambiguous)} ambiguous words, "
        f"confidence={confidence:.2f}"
    )
    return ctx


_LANGUAGE_NAMES = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
}
