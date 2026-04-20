from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.core.logging import logger
from app.models.schemas import SubtitleSegment

# ---------------------------------------------------------------------------
# Proper-noun post-correction helpers (STT output fix)
# ---------------------------------------------------------------------------


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein edit distance (O(n·m) time, O(n) space)."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            prev, dp[j] = dp[j], (
                prev if a[i - 1] == b[j - 1]
                else 1 + min(prev, dp[j], dp[j - 1])
            )
    return dp[n]


def _letters_only(text: str) -> str:
    """Return only lowercase ASCII letters from *text*."""
    return re.sub(r"[^a-z]", "", text.lower())


def _max_allowed_distance(noun_len: int) -> int:
    """Edit-distance budget for a proper noun of *noun_len* letters.

    Tuned so that a single-word name phonetically split into two words
    (e.g. "Sonam" → "So numb": distance 2) falls within tolerance, while
    short names stay strict to avoid false positives.
    """
    if noun_len <= 3:
        return 0
    if noun_len <= 7:
        return 2
    return 3


def _replace_exact(text: str, proper: str) -> tuple[str, bool]:
    """Case-insensitive exact replacement of *proper* as whole word(s)."""
    pattern = re.compile(r"\b" + re.escape(proper) + r"\b", re.IGNORECASE)
    new_text, count = pattern.subn(proper, text)
    return new_text, count > 0


def _replace_2gram(text: str, proper: str) -> tuple[str, bool]:
    """Try to find a 2-word span whose letters are a close phonetic match for *proper*.

    Designed to catch cases where Whisper splits a proper noun into two
    common words, e.g. "Sonam" → "So numb".

    Only used for single-word proper nouns (no internal space).
    Never replaces if both individual words are exact dictionary words whose
    combined edit distance to the proper noun is too high.
    """
    proper_norm = _letters_only(proper)
    if len(proper_norm) < 4:
        return text, False

    max_dist = _max_allowed_distance(len(proper_norm))
    tokens = text.split()

    if len(tokens) < 2:
        return text, False

    for i in range(len(tokens) - 1):
        w1_letters = _letters_only(tokens[i])
        w2_letters = _letters_only(tokens[i + 1])
        combined = w1_letters + w2_letters

        if not combined:
            continue

        # Length guard: skip obviously different lengths early
        if abs(len(combined) - len(proper_norm)) > max_dist + 1:
            continue

        dist = _edit_distance(combined, proper_norm)
        if dist > max_dist:
            continue

        # Similarity ratio guard — avoids borderline matches on very short nouns
        ratio = 1.0 - dist / max(len(combined), len(proper_norm))
        if ratio < 0.60:
            continue

        # Build replacement preserving surrounding punctuation
        leading = re.match(r"^(\W*)", tokens[i])
        trailing = re.search(r"(\W*)$", tokens[i + 1])
        prefix = leading.group(1) if leading else ""
        suffix = trailing.group(1) if trailing else ""

        replacement = prefix + proper + suffix
        new_tokens = tokens[:i] + [replacement] + tokens[i + 2:]
        return " ".join(new_tokens), True

    return text, False


def correct_proper_nouns_in_segments(
    segments: list[SubtitleSegment],
    proper_nouns: list[str],
) -> tuple[list[SubtitleSegment], int]:
    """Post-correct STT output using a list of known proper nouns.

    Two strategies per noun, applied in order:
    1. Case-insensitive exact word match  →  re-capitalise correctly
       (e.g. "sonam" → "Sonam", "SONAM" → "Sonam")
    2. Adjacent-word phonetic match       →  collapse two words into the name
       (e.g. "So numb" → "Sonam")
       Only for single-word proper nouns.

    Never modifies timing.  Returns (corrected_segments, corrected_count).
    corrected_count = number of segments where at least one substitution was made.
    """
    if not proper_nouns:
        return segments, 0

    corrected_count = 0
    result: list[SubtitleSegment] = []

    for seg in segments:
        text = seg.text
        changed = False

        for noun in proper_nouns:
            # Strategy 1: exact case-insensitive
            new_text, was_changed = _replace_exact(text, noun)
            if was_changed:
                text = new_text
                changed = True
                continue

            # Strategy 2: phonetic 2-gram (single-word nouns only)
            if " " not in noun:
                new_text, was_changed = _replace_2gram(text, noun)
                if was_changed:
                    text = new_text
                    changed = True

        if changed:
            corrected_count += 1

        result.append(SubtitleSegment(id=seg.id, start=seg.start, end=seg.end, text=text))

    return result, corrected_count

MIN_SEGMENT_DURATION = 0.3  # seconds
MAX_GAP_FOR_MERGE = 0.15  # seconds

_MAX_LINE_CHARS = 42   # standard Netflix/broadcast

# Hard cap on display duration (Netflix standard: 7s max per card)
_MAX_DISPLAY_DURATION = 7.0
# Reading speed for natural duration estimation
_CHARS_PER_SECOND = 20.0
_MIN_DISPLAY_DURATION = 1.5  # minimum comfortable reading time

# Whisper hallucination patterns — these appear on silent/music sections
_HALLUCINATION_PATTERNS = [
    re.compile(r"^thank(s| you)?\s*(for\s*(watching|listening|viewing))?\s*[.!]*$", re.IGNORECASE),
    re.compile(r"^please\s*(subscribe|like|share)", re.IGNORECASE),
    re.compile(r"^(sub(scribe|s)|like|share|comment)\s*(and\s*)?(sub(scribe|s)|like|share|comment)?", re.IGNORECASE),
    re.compile(r"^(see you|bye|goodbye)\s*(next time|in the next)?\s*[.!]*$", re.IGNORECASE),
    re.compile(r"^\.*$"),  # just dots
    re.compile(r"^♪+$"),  # just music notes
    re.compile(r"^(www\.|https?://)\S+", re.IGNORECASE),  # URLs
    re.compile(r"^(subtitles?|captions?|translation|transcript)\s*(by|:|from|made)", re.IGNORECASE),  # credit lines
    re.compile(r"^(downloaded|synced?|corrected?|encoded?)\s+(by|from|at|with)\s+", re.IGNORECASE),  # rip tags
    re.compile(r"^[\s♪\-_=*#.]{1,4}$"),  # only decorative chars (1–4)
    # Watermarks: ALL-CAPS words + 4-digit year (e.g. "BF WATCH TV 2021", "HDTV 2023")
    re.compile(r"^[A-Z0-9][A-Z0-9\s.\-]{2,50}\b(19|20)\d{2}\b\s*$"),
    # Release/fansub group tags: [FGT], (YIFY), [BluRay.x265], etc.
    re.compile(r"^[\[\(][^\]\)\n]{1,40}[\]\)]\s*$"),
    # Repeated phrase: "I love you I love you" or "Hmm hmm hmm"
    re.compile(r"^(.{4,30})\s+\1\s*$"),
    # Decorative separator lines: ===title===, ---EOF---, *** end ***
    re.compile(r"^[-=*_~<>]{2,}\s*\S.*\S\s*[-=*_~<>]{2,}$"),
    # Amara / community caption credit sites
    re.compile(r"amara\.org|opensubtitles|subscene|yifysubtitles", re.IGNORECASE),
]

# Annotations Whisper sometimes inserts — not actual speech
_ANNOTATION_PATTERN = re.compile(
    r"^\[.*\]$|^\(.*\)$"  # [Music], [Applause], (inaudible), etc.
)

# Threshold for considering two segments as duplicates (0.0–1.0)
_DUPLICATE_SIMILARITY = 0.85

# Duration hallucination: more than N seconds per word is implausible speech
_MAX_SECONDS_PER_WORD = 8.0
# Minimum duration to even bother checking (short segments are fine)
_MIN_DURATION_FOR_HALLUCINATION_CHECK = 12.0

# Short-text duration check: catches "I love you." on 15s of silence
# (too few words for the standard 8s/word rule to trigger)
_SHORT_TEXT_MAX_WORDS = 5       # only applies to segments with ≤ 5 words
_SHORT_TEXT_MIN_DURATION = 10.0  # don't flag if under 10s (legitimate pause)
_SHORT_TEXT_MAX_SPW = 4.5       # flag if duration / word_count exceeds this

# End-of-content zone: last N% of the timeline gets stricter hallucination filtering.
# Whisper generates the most noise during end credits / silence after the last line.
_END_ZONE_FRACTION = 0.97       # segments starting after 97% of total duration
_END_ZONE_MAX_SPW = 3.0         # stricter spw threshold in end zone
_END_ZONE_MIN_DURATION = 5.0    # apply stricter check only if duration ≥ 5s

# Multi-speaker: segments longer than this word count get a line-break heuristic
_MULTI_SPEAKER_MIN_WORDS = 16
# Interjections that often signal a new speaker turn
_SPEAKER_STARTER = re.compile(
    r"(?<=[a-z,])\s+(Oh|Well|Hey|Ah|So|Now|But|No|Yes|Look|Wait|Come|Go|Please|Sorry)\s+",
    re.IGNORECASE,
)


def _find_split(text: str) -> int | None:
    """Find best char index to split a long line near its middle."""
    mid = len(text) // 2
    candidates: list[int] = []

    # Prefer break after sentence-end punctuation
    for m in re.finditer(r'(?<=[.!?])\s+', text):
        candidates.append(m.start())
    # Prefer break before conjunction
    for m in re.finditer(
        r'\s+(?=(?:and|but|or|so|yet|because|when|while|if|that|which|who)\b)',
        text, re.IGNORECASE
    ):
        candidates.append(m.start())
    # After comma
    for m in re.finditer(r'(?<=,)\s+', text):
        candidates.append(m.start())
    # Any space
    for m in re.finditer(r'\s+', text):
        candidates.append(m.start())

    if not candidates:
        return None

    # Closest to midpoint, slightly biased toward first half
    best = min(candidates, key=lambda p: abs(p - mid) + (0.1 if p > mid else 0))
    return best if 0 < best < len(text) else None


def _reflow_text(text: str) -> str:
    """Enforce max 2 lines of _MAX_LINE_CHARS each."""
    raw_lines = [l.strip() for l in text.split('\n') if l.strip()]
    out: list[str] = []

    for line in raw_lines:
        if len(out) >= 2:
            break  # already 2 lines, discard overflow
        if len(line) <= _MAX_LINE_CHARS:
            out.append(line)
        else:
            sp = _find_split(line)
            if sp:
                out.append(line[:sp].rstrip())
                if len(out) < 2:
                    out.append(line[sp:].lstrip())
            else:
                out.append(line)  # can't split cleanly, keep as-is

    return '\n'.join(out) if out else text


def reflow_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Enforce max 2 lines × 42 chars per subtitle card."""
    result = [
        SubtitleSegment(id=s.id, start=s.start, end=s.end, text=_reflow_text(s.text))
        for s in segments
    ]
    return result


def clean_imported_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Light cleanup for user-provided subtitle files (no hallucination filters)."""
    result = segments
    result = remove_empty_segments(result)
    result = trim_text(result)
    result = fix_negative_timecodes(result)
    result = fix_invalid_durations(result)
    result = sort_chronologically(result)
    result = fix_overlaps(result)
    result = reflow_segments(result)
    result = clean_punctuation(result)
    result = reindex(result)
    return result


def clean_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Apply all post-processing rules to subtitle segments."""
    original_count = len(segments)
    result = segments
    result = remove_empty_segments(result)
    result = trim_text(result)
    result = remove_annotations(result)
    result = remove_hallucinations(result)
    result = remove_duration_hallucinations(result)
    result = fix_negative_timecodes(result)
    result = fix_invalid_durations(result)
    result = sort_chronologically(result)
    result = filter_end_of_content(result)
    result = fix_overlaps(result)
    result = cap_display_duration(result)
    result = deduplicate_boundary_segments(result)
    result = merge_short_segments(result)
    result = split_multi_speaker(result)
    result = reflow_segments(result)
    result = clean_punctuation(result)
    result = capitalize_sentences(result)
    result = reindex(result)
    logger.info(f"Post-processing: {original_count} -> {len(result)} segments")
    return result


def remove_empty_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [s for s in segments if s.text and s.text.strip()]


def trim_text(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [
        SubtitleSegment(id=s.id, start=s.start, end=s.end, text=s.text.strip())
        for s in segments
    ]


def remove_annotations(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Remove Whisper annotations like [Music], [Applause], (inaudible)."""
    kept = []
    removed = 0
    for s in segments:
        if _ANNOTATION_PATTERN.match(s.text.strip()):
            removed += 1
        else:
            kept.append(s)
    if removed:
        logger.info(f"Removed {removed} annotation segments (e.g. [Music])")
    return kept


def remove_hallucinations(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Remove known Whisper hallucination patterns."""
    kept = []
    removed = 0
    for s in segments:
        text = s.text.strip()
        if any(p.match(text) for p in _HALLUCINATION_PATTERNS):
            removed += 1
        else:
            kept.append(s)
    if removed:
        logger.info(f"Removed {removed} likely hallucinated segments")
    return kept


def remove_duration_hallucinations(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Remove segments where duration is implausibly long relative to text length.

    Two checks:
    1. Standard: duration > 12s AND > 8s/word (dense speech check)
    2. Short-text: ≤5 words, duration ≥ 10s, > 4.5s/word
       Catches "I love you." over 15s of music/silence that the standard
       rule misses (3 words × 8s = 24s threshold, but 15s slips through).
    """
    kept = []
    removed = 0
    for s in segments:
        duration = s.end - s.start
        word_count = len(s.text.split())

        if word_count == 0:
            removed += 1
            continue

        spw = duration / word_count

        # Standard check — long segments with high s/word ratio
        if duration >= _MIN_DURATION_FOR_HALLUCINATION_CHECK and spw > _MAX_SECONDS_PER_WORD:
            removed += 1
            logger.debug(
                f"Duration hallucination (standard): '{s.text}' "
                f"({duration:.1f}s / {word_count}w = {spw:.1f}s/w)"
            )
            continue

        # Short-text check — few words, long silence, suspicious s/word
        if (
            word_count <= _SHORT_TEXT_MAX_WORDS
            and duration >= _SHORT_TEXT_MIN_DURATION
            and spw > _SHORT_TEXT_MAX_SPW
        ):
            removed += 1
            logger.debug(
                f"Duration hallucination (short-text): '{s.text}' "
                f"({duration:.1f}s / {word_count}w = {spw:.1f}s/w)"
            )
            continue

        kept.append(s)

    if removed:
        logger.info(f"Removed {removed} duration-hallucinated segments")
    return kept


def split_multi_speaker(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Add a line break in long segments that appear to contain multiple speakers.

    Looks for interjection words that typically start a new speaker turn
    (Oh, Well, Hey, etc.) after the first quarter of the text. Falls back to
    a midpoint split for very long segments with no such marker.
    """
    result = []
    split_count = 0
    for s in segments:
        words = s.text.split()
        # Only process long segments with no existing line break
        if len(words) < _MULTI_SPEAKER_MIN_WORDS or "\n" in s.text:
            result.append(s)
            continue

        # Skip if the segment already has natural sentence boundaries
        if re.search(r"[.!?]\s+[A-Z]", s.text):
            result.append(s)
            continue

        new_text: str | None = None

        # Look for a speaker-starter interjection after the first quarter
        quarter = len(" ".join(words[: len(words) // 4]))
        tail = s.text[quarter:]
        match = _SPEAKER_STARTER.search(tail)
        if match:
            split_at = quarter + match.start() + 1  # +1 to skip the space before
            new_text = s.text[:split_at].rstrip() + "\n- " + s.text[split_at:].lstrip()
        elif len(words) > 22:
            # Midpoint split for very long segments with no marker
            mid = len(words) // 2
            new_text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])

        if new_text:
            result.append(SubtitleSegment(id=s.id, start=s.start, end=s.end, text=new_text))
            split_count += 1
        else:
            result.append(s)

    if split_count:
        logger.info(f"Added line breaks to {split_count} multi-speaker segment(s)")
    return result


def cap_display_duration(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Cap segment display time to a readable maximum.

    Two caps applied:
    1. Hard max: 7s (Netflix standard) — never exceeded
    2. Word-proportional soft cap: if duration > 3× natural reading time AND > 4s,
       trim to 1.5× natural. Catches short text stuck on screen too long without
       hitting the 7s hard max (e.g. "Yes." displayed for 6s).

    Natural duration = max(1.5s, word_count × 0.7s + 0.8s buffer)
    """
    result = []
    capped = 0
    for s in segments:
        current = s.end - s.start
        text = s.text.replace("\n", " ").strip()
        word_count = len(text.split())

        # Natural reading duration based on word count
        natural = max(_MIN_DISPLAY_DURATION, word_count * 0.7 + 0.8)

        if current > _MAX_DISPLAY_DURATION:
            # Hard cap
            result.append(SubtitleSegment(id=s.id, start=s.start, end=s.start + _MAX_DISPLAY_DURATION, text=s.text))
            capped += 1
        elif current > natural * 3.0 and current > 4.0:
            # Soft word-proportional cap (only if meaningfully over-long)
            new_duration = min(_MAX_DISPLAY_DURATION, natural * 1.5)
            result.append(SubtitleSegment(id=s.id, start=s.start, end=s.start + new_duration, text=s.text))
            capped += 1
        else:
            result.append(s)

    if capped:
        logger.info(f"Capped display duration on {capped} segment(s)")
    return result


def filter_end_of_content(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Apply stricter hallucination rules to the last ~3% of the timeline.

    Whisper generates the most noise during end credits, long silence after the
    last spoken line, and music-only sections at the end of a film. Any segment
    in this zone that has an implausibly high s/word ratio is removed.

    No VAD is used — this is a timing heuristic only.
    """
    if len(segments) < 10:
        return segments

    last_ts = max(s.start for s in segments)
    threshold = last_ts * _END_ZONE_FRACTION

    kept = []
    removed = 0
    for s in segments:
        if s.start < threshold:
            kept.append(s)
            continue

        duration = s.end - s.start
        word_count = len(s.text.split())

        if word_count == 0:
            removed += 1
            continue

        spw = duration / word_count
        # Stricter s/word threshold in the end zone
        if duration >= _END_ZONE_MIN_DURATION and spw > _END_ZONE_MAX_SPW:
            removed += 1
            logger.debug(
                f"End-zone hallucination: '{s.text}' "
                f"({duration:.1f}s / {word_count}w = {spw:.1f}s/w, "
                f"starts at {s.start:.1f}s / threshold {threshold:.1f}s)"
            )
            continue

        kept.append(s)

    if removed:
        logger.info(f"Removed {removed} end-of-content hallucination(s)")
    return kept


def deduplicate_boundary_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Remove near-duplicate segments at chunk boundaries.

    When audio is split into overlapping chunks, Whisper often transcribes
    the same speech twice at the boundary. We detect these by checking
    consecutive segments with similar timestamps and similar text.
    """
    if len(segments) < 2:
        return segments

    kept: list[SubtitleSegment] = [segments[0]]
    removed = 0

    for seg in segments[1:]:
        prev = kept[-1]

        # Only check segments that are close in time (within 2s of each other)
        time_close = abs(seg.start - prev.start) < 2.0

        if time_close:
            similarity = SequenceMatcher(None, prev.text.lower(), seg.text.lower()).ratio()
            if similarity >= _DUPLICATE_SIMILARITY:
                # Keep the longer one (usually more complete)
                if len(seg.text) > len(prev.text):
                    kept[-1] = seg
                removed += 1
                continue

        kept.append(seg)

    if removed:
        logger.info(f"Removed {removed} duplicate boundary segments")
    return kept


def fix_negative_timecodes(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [
        SubtitleSegment(
            id=s.id,
            start=max(0.0, s.start),
            end=max(0.0, s.end),
            text=s.text,
        )
        for s in segments
    ]


def fix_invalid_durations(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Remove segments where end <= start."""
    return [s for s in segments if s.end > s.start]


def sort_chronologically(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return sorted(segments, key=lambda s: s.start)


def fix_overlaps(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Fix overlapping segments by trimming the end of the earlier segment."""
    if len(segments) < 2:
        return segments
    fixed = [segments[0]]
    for seg in segments[1:]:
        prev = fixed[-1]
        if prev.end > seg.start:
            fixed[-1] = SubtitleSegment(
                id=prev.id,
                start=prev.start,
                end=seg.start,
                text=prev.text,
            )
        fixed.append(seg)
    return [s for s in fixed if s.end > s.start]


def merge_short_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Merge very short segments with the next segment if gap is small."""
    if len(segments) < 2:
        return segments

    merged: list[SubtitleSegment] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        duration = seg.end - seg.start
        if (
            duration < MIN_SEGMENT_DURATION
            and i + 1 < len(segments)
            and segments[i + 1].start - seg.end < MAX_GAP_FOR_MERGE
        ):
            next_seg = segments[i + 1]
            merged.append(
                SubtitleSegment(
                    id=seg.id,
                    start=seg.start,
                    end=next_seg.end,
                    text=f"{seg.text} {next_seg.text}",
                )
            )
            i += 2
        else:
            merged.append(seg)
            i += 1
    return merged


def clean_punctuation(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Clean obvious punctuation issues."""
    result = []
    for s in segments:
        text = s.text
        # Remove multiple spaces
        text = re.sub(r" {2,}", " ", text)
        # Remove leading/trailing punctuation oddities
        text = re.sub(r"^[,;:\s]+", "", text)
        # Fix multiple periods
        text = re.sub(r"\.{4,}", "...", text)
        # Remove trailing comma
        text = re.sub(r",\s*$", ".", text)
        text = text.strip()
        if text:
            result.append(SubtitleSegment(id=s.id, start=s.start, end=s.end, text=text))
    return result


def capitalize_sentences(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Ensure each segment starts with a capital letter."""
    result = []
    for s in segments:
        text = s.text
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        result.append(SubtitleSegment(id=s.id, start=s.start, end=s.end, text=text))
    return result


def reindex(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [
        SubtitleSegment(id=i, start=s.start, end=s.end, text=s.text)
        for i, s in enumerate(segments, start=1)
    ]
