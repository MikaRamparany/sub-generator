from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger


def get_video_base_name(video_path: str) -> str:
    """Extract base name without extension from video path."""
    return Path(video_path).stem


def get_export_filename(video_path: str, language: str, fmt: str) -> str:
    """Generate export filename following convention: name.lang.ext"""
    base = get_video_base_name(video_path)
    return f"{base}.{language}.{fmt}"


def validate_video_path(video_path: str) -> Path:
    """Validate that the video path exists and has a supported format."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {video_path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {video_path}")
    ext = path.suffix.lstrip(".").lower()
    if ext not in settings.supported_formats:
        raise ValueError(f"Unsupported format: {ext}. Supported: {settings.supported_formats}")
    return path


def cleanup_directory(dir_path: Path) -> None:
    """Remove a temporary directory and all its contents."""
    if settings.debug_keep_temp_files:
        logger.info(f"Debug mode: keeping temp files at {dir_path}")
        return
    if dir_path.exists():
        shutil.rmtree(dir_path, ignore_errors=True)
        logger.info(f"Cleaned up temp directory: {dir_path}")


def ensure_dir(dir_path: Path) -> Path:
    """Ensure directory exists."""
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def file_size_mb(file_path: str | Path) -> float:
    """Return file size in megabytes."""
    return os.path.getsize(file_path) / (1024 * 1024)
