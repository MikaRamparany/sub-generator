from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.utils.filesystem import file_size_mb


class AudioChunk:
    def __init__(self, path: str, offset_seconds: float):
        self.path = path
        self.offset_seconds = offset_seconds


def needs_chunking(audio_path: str) -> bool:
    """Check if audio file exceeds the max chunk size for the API."""
    size = file_size_mb(audio_path)
    return size > settings.max_api_audio_chunk_mb


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    return float(result.stdout.strip())


def chunk_audio(audio_path: str, output_dir: str) -> list[AudioChunk]:
    """Split audio into chunks that fit within API size limits.

    Uses duration-based splitting to produce chunks under the max size.
    Each chunk gets a 0.5s overlap to avoid cutting mid-word.
    """
    total_size_mb = file_size_mb(audio_path)
    total_duration = get_audio_duration(audio_path)

    # Estimate chunk duration based on file size ratio
    max_chunk_mb = settings.max_api_audio_chunk_mb * 0.9  # 10% safety margin
    num_chunks = max(1, int(total_size_mb / max_chunk_mb) + 1)
    chunk_duration = total_duration / num_chunks

    logger.info(
        f"Chunking audio: {total_size_mb:.1f}MB, {total_duration:.1f}s -> "
        f"{num_chunks} chunks of ~{chunk_duration:.1f}s"
    )

    chunks: list[AudioChunk] = []
    output_path = Path(output_dir)

    for i in range(num_chunks):
        start = i * chunk_duration
        chunk_file = str(output_path / f"chunk_{i:04d}.wav")

        cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_path,
            "-ss", str(start),
            "-t", str(chunk_duration + 0.5),  # small overlap
            "-ac", "1",
            "-ar", "16000",
            "-acodec", "pcm_s16le",
            chunk_file,
        ]

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create chunk {i}: {e.stderr[:300]}")

        if Path(chunk_file).exists():
            chunks.append(AudioChunk(path=chunk_file, offset_seconds=start))
            logger.info(f"Created chunk {i}: offset={start:.1f}s")

    if not chunks:
        raise RuntimeError("Audio chunking produced no output files")

    return chunks
