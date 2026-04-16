"""Translation QA pass — detect, score, and retranslate suspect translations.

Two-phase QA pipeline:
1. Score every segment (0 = fine, higher = more suspect)
2. Sort suspects by score, retranslate the worst N via Groq with context
Plus a terminological consistency pass that flags same-source → different-target
inconsistencies for inclusion in the suspect queue.

Replaces the old "all or nothing" logic: if there are 66 suspects with a limit
of 60, we now retranslate the 60 worst ones and silently skip the 6 least suspect.

Never blocks the pipeline — all Groq failures degrade gracefully to keeping
the original translation.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.context import TranscriptContext
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

# Context window for retranslation (neighbour segments shown to the LLM)
_CONTEXT_WINDOW = 3
# Max suspects to retranslate (those with the highest scores are prioritised)
_MAX_QA_SEGMENTS = 60
# Delay between Groq calls in the QA pass
_QA_INTER_DELAY = 2.5     # ~24 RPM — stays under Groq free tier limit (30 RPM)
_QA_RETRIES = 2

# Minimum occurrences for consistency check
_CONSISTENCY_MIN_OCCURRENCES = 3

# Common interjections / reactions that are legitimately identical in many languages
_INTERJECTIONS = frozenset({
    "oh", "ah", "hey", "wow", "hmm", "hm", "uh", "um", "yeah", "yep",
    "nope", "ok", "okay", "no", "yes", "hi", "bye", "whoa", "ow",
    "oops", "ouch", "shh", "ssh", "mhm", "aha",
})

# English function words — used to detect residual English in a non-English target
_EN_FUNCTION_WORDS = frozenset({
    "the", "is", "are", "was", "were", "have", "has", "been", "will",
    "would", "could", "should", "this", "that", "these", "those",
    "with", "from", "they", "their", "there", "what", "when", "where",
    "which", "who", "whom", "whose", "you", "your",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text).lower().strip()


def is_legitimate_identical(src: str, tgt: str) -> bool:
    """Return True when source == target is acceptable (not a translation failure).

    Covers: proper nouns (single capitalised word), interjections, pure numbers/codes.
    Used both in QA scoring and in the job_manager fallback counter.
    """
    src_s = src.strip().rstrip(".,!?…")
    tgt_s = tgt.strip().rstrip(".,!?…")

    if src_s.lower() != tgt_s.lower():
        return False  # texts differ — not our concern here

    words = src_s.split()

    # Single capitalised word → likely a proper noun / name
    if len(words) == 1 and src_s and src_s[0].isupper() and src_s[1:].islower():
        return True

    # All-caps short word → acronym / code (APEX, FBI, etc.)
    if len(words) == 1 and src_s.isupper() and len(src_s) <= 6:
        return True

    # Known interjection
    if _strip_punct(src_s) in _INTERJECTIONS:
        return True

    # Pure number / code
    if re.match(r"^[\d\s\-\.\,\+\(\)\/]+$", src_s):
        return True

    # Multi-word but all words are capitalised (likely a proper name / title)
    if len(words) >= 2 and all(w[0].isupper() for w in words if w):
        return True

    return False


def _has_residual_english(text: str, target_language: str) -> bool:
    """Heuristic: detect residual English in a non-English translation."""
    if target_language == "en":
        return False
    words = {w.lower().strip(".,!?\"'") for w in text.split()}
    return len(words & _EN_FUNCTION_WORDS) >= 2


def _score_segment(seg: TranslatedSubtitleSegment) -> float:
    """Return a suspicion score for a translated segment.

    0.0  → looks fine
    >0   → suspect (higher = more urgent to retranslate)

    Score components (cumulative):
      10.0  exact source == target, not a legitimate identical
       8.0  stripped-punct identical, short segment (≤3 words)
       6.0  long source, very short target (< 45 % words) — likely truncated
       4.0  residual English detected in target
       3.0  long source, somewhat short target (45–60 %)
    """
    src = seg.source_text.strip()
    tgt = seg.translated_text.strip()

    if not src or not tgt:
        return 0.0

    if is_legitimate_identical(src, tgt):
        return 0.0

    score = 0.0
    src_words = src.split()
    tgt_words = tgt.split()

    if src.lower() == tgt.lower():
        score += 10.0
    elif len(src_words) <= 3 and _strip_punct(src) == _strip_punct(tgt):
        score += 8.0
    elif len(src_words) >= 7 and len(tgt_words) < len(src_words) * 0.45:
        score += 6.0
    elif len(src_words) >= 7 and len(tgt_words) < len(src_words) * 0.60:
        score += 3.0

    if _has_residual_english(tgt, seg.target_language):
        score += 4.0

    return score


# ---------------------------------------------------------------------------
# Consistency pass
# ---------------------------------------------------------------------------

def detect_terminology_inconsistencies(
    translated: list[TranslatedSubtitleSegment],
    min_occurrences: int = _CONSISTENCY_MIN_OCCURRENCES,
) -> list[int]:
    """Return indices of segments with inconsistent translations of recurring terms.

    For every short (≤2 words) source term that appears ≥ min_occurrences times,
    check whether it is translated consistently. Minority-translation segments are
    flagged as suspects for QA.

    Pure Python — no API calls.
    """
    from collections import defaultdict

    src_to_occurrences: dict[str, list[tuple[int, str]]] = defaultdict(list)

    for idx, seg in enumerate(translated):
        src_lower = seg.source_text.strip().lower()
        tgt = seg.translated_text.strip()
        if len(src_lower.split()) <= 2:
            src_to_occurrences[src_lower].append((idx, tgt))

    inconsistent: set[int] = set()

    for src_term, occurrences in src_to_occurrences.items():
        if len(occurrences) < min_occurrences:
            continue

        tgt_lower = [tgt.lower() for _, tgt in occurrences]
        unique = set(tgt_lower)
        if len(unique) <= 1:
            continue  # perfectly consistent

        counts = Counter(tgt_lower)
        majority_tgt, majority_count = counts.most_common(1)[0]
        minority = [idx for idx, tgt in occurrences if tgt.lower() != majority_tgt]

        if minority:
            logger.debug(
                f"Consistency: '{src_term}' → majority='{majority_tgt}' ({majority_count}x), "
                f"{len(minority)} inconsistent segment(s)"
            )
            inconsistent.update(minority)

    return list(inconsistent)


# ---------------------------------------------------------------------------
# Main QA entry point
# ---------------------------------------------------------------------------

async def qa_retranslate(
    translated: list[TranslatedSubtitleSegment],
    target_language: str,
    source_language: str | None = None,
    transcript_context: TranscriptContext | None = None,
    max_retranslate: int = _MAX_QA_SEGMENTS,
) -> list[TranslatedSubtitleSegment]:
    """Score, prioritise, and retranslate the worst suspect segments via Groq.

    Steps:
    1. Score every segment
    2. Merge in consistency-pass suspects (scored at 2.0 if not already suspect)
    3. Sort by score descending → take top max_retranslate
    4. Retranslate each with ±CONTEXT_WINDOW neighbours as context
    5. Return a new list (original never mutated)
    """
    if not settings.groq_api_key:
        logger.debug("QA retranslation skipped: GROQ_API_KEY not configured")
        return translated

    # Step 1: score all segments
    scores: dict[int, float] = {}
    for idx, seg in enumerate(translated):
        s = _score_segment(seg)
        if s > 0.0:
            scores[idx] = s

    # Step 2: merge consistency suspects (base score 2.0 if not already scored higher)
    consistency_suspects = detect_terminology_inconsistencies(translated)
    for idx in consistency_suspects:
        if idx not in scores:
            scores[idx] = 2.0
        # else: keep the higher score from _score_segment

    total_suspects = len(scores)
    if total_suspects == 0:
        logger.info("QA pass: no suspect translations found")
        return translated

    # Step 3: sort by score desc, take top N
    prioritised = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_retranslate]
    skipped = total_suspects - len(prioritised)

    logger.info(
        f"QA pass: {total_suspects} suspect segment(s) detected — "
        f"retranslating top {len(prioritised)}"
        + (f", skipping {skipped} lower-priority" if skipped else "")
    )

    # Step 4: retranslate
    result = list(translated)
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)
    context_hint = (
        transcript_context.to_glossary_hint(target_language)
        if transcript_context and transcript_context.is_useful()
        else ""
    )

    improved = 0
    for call_idx, (seg_idx, score) in enumerate(prioritised):
        if call_idx > 0:
            await asyncio.sleep(_QA_INTER_DELAY)

        seg = translated[seg_idx]

        ctx_start = max(0, seg_idx - _CONTEXT_WINDOW)
        ctx_end = min(len(translated), seg_idx + _CONTEXT_WINDOW + 1)
        context_segs = [
            translated[i] for i in range(ctx_start, ctx_end) if i != seg_idx
        ]
        local_context = "\n".join(
            f'[{s.start:.1f}s] "{s.translated_text}"' for s in context_segs
        )

        retranslated = await _retranslate_one(
            seg, lang_name, source_language, local_context, context_hint
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
            improved += 1
            logger.debug(
                f"QA fixed seg {seg.id} (score={score:.1f}): "
                f"{seg.source_text!r} → {retranslated!r}"
            )

    logger.info(
        f"QA pass complete: {improved}/{len(prioritised)} segment(s) improved"
    )
    return result


# ---------------------------------------------------------------------------
# Single-segment retranslation
# ---------------------------------------------------------------------------

async def _retranslate_one(
    seg: TranslatedSubtitleSegment,
    lang_name: str,
    source_language: str | None,
    local_context: str,
    global_context_hint: str,
) -> str | None:
    """Retranslate one segment with Groq. Returns new text or None on failure."""
    model = settings.groq_translation_model

    source_hint = ""
    if source_language and source_language != "auto":
        src_name = LANGUAGE_NAMES.get(source_language, source_language)
        source_hint = f" The source language is {src_name}."

    global_block = (
        f"\n\nGlobal context (inferred from transcript):\n{global_context_hint}"
        if global_context_hint
        else ""
    )
    local_block = (
        f"\n\nSurrounding translated lines (context — do NOT retranslate):\n{local_context}"
        if local_context
        else ""
    )

    prompt = (
        f"Translate this single movie subtitle line to {lang_name}.{source_hint}\n"
        f"Return ONLY the translated text — no JSON, no explanation, no quotes.\n"
        f"Natural and idiomatic — write as a native {lang_name} speaker would say it."
        f"{global_block}{local_block}\n\n"
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
            logger.warning(f"QA network error: {e}")
            return None

        if response.status_code == 429:
            if attempt < _QA_RETRIES:
                wait = float(response.headers.get("retry-after", 10))
                logger.warning(f"QA 429 — waiting {wait:.0f}s")
                await asyncio.sleep(wait)
                continue
            logger.warning("QA rate-limited — keeping original")
            return None

        if response.status_code != 200:
            logger.warning(
                f"QA API error {response.status_code}: {response.text[:200]}"
            )
            return None

        text = response.json()["choices"][0]["message"]["content"].strip()

        if not text:
            return None

        # Discard if LLM echoed the source unchanged
        if text.lower() == seg.source_text.lower():
            return None

        # Strip surrounding quotes the LLM sometimes adds
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1].strip()

        return text or None

    return None
