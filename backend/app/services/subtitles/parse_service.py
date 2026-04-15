from __future__ import annotations

import re
from pathlib import Path

from app.core.logging import logger
from app.models.schemas import SubtitleSegment

# SRT timestamp: 00:01:23,456
_SRT_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})")

# VTT timestamp: 00:01:23.456
_VTT_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})")

# Arrow separator used in both formats
_ARROW = re.compile(r"\s*-->\s*")


def _parse_timestamp(raw: str) -> float | None:
    """Parse an SRT or VTT timestamp to seconds."""
    m = _SRT_TS.match(raw.strip()) or _VTT_TS.match(raw.strip())
    if not m:
        return None
    h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return h * 3600 + mi * 60 + s + ms / 1000


def parse_subtitle_file(file_path: str) -> list[SubtitleSegment]:
    """Parse an SRT or VTT file and return subtitle segments."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {file_path}")

    ext = path.suffix.lower()
    if ext not in (".srt", ".vtt"):
        raise ValueError(f"Unsupported subtitle format: {ext} (expected .srt or .vtt)")

    content = path.read_text(encoding="utf-8", errors="replace")

    # VTT files start with WEBVTT header — skip it
    if ext == ".vtt":
        lines = content.split("\n")
        # Find first line after WEBVTT header and any metadata
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip().upper().startswith("WEBVTT"):
                start_idx = i + 1
                break
        # Skip blank lines and NOTE blocks after header
        while start_idx < len(lines) and (
            not lines[start_idx].strip() or lines[start_idx].strip().startswith("NOTE")
        ):
            start_idx += 1
        content = "\n".join(lines[start_idx:])

    segments = _parse_blocks(content)
    logger.info(f"Parsed {len(segments)} segments from {path.name}")
    return segments


def _parse_blocks(content: str) -> list[SubtitleSegment]:
    """Parse subtitle blocks from SRT/VTT content."""
    # Split by double newlines (block separator)
    blocks = re.split(r"\n\s*\n", content.strip())

    segments: list[SubtitleSegment] = []
    seg_id = 1

    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue

        # Find the timestamp line (contains "-->")
        ts_line_idx = None
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line_idx = i
                break

        if ts_line_idx is None:
            continue

        # Parse timestamps
        parts = _ARROW.split(lines[ts_line_idx], maxsplit=1)
        if len(parts) != 2:
            continue

        start = _parse_timestamp(parts[0])
        end = _parse_timestamp(parts[1])
        if start is None or end is None:
            continue

        # Text is everything after the timestamp line
        text_lines = lines[ts_line_idx + 1:]
        text = " ".join(text_lines).strip()
        if not text:
            continue

        segments.append(SubtitleSegment(id=seg_id, start=start, end=end, text=text))
        seg_id += 1

    return segments
