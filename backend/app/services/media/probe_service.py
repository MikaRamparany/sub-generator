from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.core.logging import logger
from app.models.schemas import AudioTrack, ProbeResult
from app.utils.filesystem import file_size_mb


def check_ffprobe_available() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def probe_video(video_path: str) -> ProbeResult:
    """Probe a video file using ffprobe and return structured metadata."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    logger.info(f"Probing video: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError("ffprobe is not installed or not in PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffprobe timed out while analyzing the video")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr}")

    data = json.loads(result.stdout)

    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0))
    format_name = fmt.get("format_name", "unknown")

    audio_tracks: list[AudioTrack] = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            tags = stream.get("tags", {})
            audio_tracks.append(
                AudioTrack(
                    index=stream.get("index", 0),
                    codec=stream.get("codec_name"),
                    channels=stream.get("channels"),
                    language=tags.get("language"),
                )
            )

    if not audio_tracks:
        raise ValueError("No audio tracks found in the video")

    ext = path.suffix.lstrip(".").lower()

    return ProbeResult(
        file_name=path.name,
        file_size_mb=round(file_size_mb(video_path), 2),
        duration_seconds=round(duration, 2),
        video_format=ext or format_name,
        audio_tracks=audio_tracks,
    )
