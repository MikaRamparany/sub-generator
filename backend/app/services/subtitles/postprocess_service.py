from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.core.logging import logger
from app.models.schemas import SubtitleSegment

MIN_SEGMENT_DURATION = 0.3  # seconds
MAX_GAP_FOR_MERGE = 0.15  # seconds

# Whisper hallucination patterns — these appear on silent/music sections
_HALLUCINATION_PATTERNS = [
    re.compile(r"^thank(s| you)?\s*(for\s*(watching|listening|viewing))?\s*[.!]*$", re.IGNORECASE),
    re.compile(r"^please\s*(subscribe|like|share)", re.IGNORECASE),
    re.compile(r"^(sub(scribe|s)|like|share|comment)\s*(and\s*)?(sub(scribe|s)|like|share|comment)?", re.IGNORECASE),
    re.compile(r"^(see you|bye|goodbye)\s*(next time|in the next)?\s*[.!]*$", re.IGNORECASE),
    re.compile(r"^\.*$"),  # just dots
    re.compile(r"^♪+$"),  # just music notes
]

# Annotations Whisper sometimes inserts — not actual speech
_ANNOTATION_PATTERN = re.compile(
    r"^\[.*\]$|^\(.*\)$"  # [Music], [Applause], (inaudible), etc.
)

# Threshold for considering two segments as duplicates (0.0–1.0)
_DUPLICATE_SIMILARITY = 0.85


def clean_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Apply all post-processing rules to subtitle segments."""
    original_count = len(segments)
    result = segments
    result = remove_empty_segments(result)
    result = trim_text(result)
    result = remove_annotations(result)
    result = remove_hallucinations(result)
    result = fix_negative_timecodes(result)
    result = fix_invalid_durations(result)
    result = sort_chronologically(result)
    result = fix_overlaps(result)
    result = deduplicate_boundary_segments(result)
    result = merge_short_segments(result)
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
