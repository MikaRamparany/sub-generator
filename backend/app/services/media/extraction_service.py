from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.logging import logger


def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def extract_audio(
    video_path: str,
    output_path: str,
    audio_track_index: int = 0,
) -> str:
    """Extract audio from video, converting to WAV mono 16kHz for STT compatibility."""
    logger.info(f"Extracting audio track {audio_track_index} from {video_path}")

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(path),
        "-map", f"0:{audio_track_index}",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=600
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg is not installed or not in PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out during audio extraction")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Audio extraction failed: {e.stderr[:500]}")

    if not Path(output_path).exists():
        raise RuntimeError("Audio extraction produced no output file")

    logger.info(f"Audio extracted to {output_path}")
    return output_path
