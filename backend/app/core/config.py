from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    deepl_api_key: str = ""  # if set, DeepL is used for translation instead of Groq LLM

    # Two explicit STT models — fast uses a lighter/faster Whisper variant,
    # high_quality uses the large model with deterministic decoding (temperature=0).
    # Set both to the same value if only one model is available on your Groq plan.
    groq_stt_fast_model: str = "whisper-large-v3-turbo"
    groq_stt_quality_model: str = "whisper-large-v3"

    groq_translation_model: str = "llama-3.3-70b-versatile"

    max_upload_mb: int = 2048
    max_api_audio_chunk_mb: int = 25

    temp_dir: str = ""
    log_level: str = "INFO"
    debug_keep_temp_files: bool = False

    supported_formats: list[str] = ["mp4", "mov", "mkv", "avi", "webm"]
    supported_languages: list[str] = ["fr", "en", "es", "de"]

    model_config = {
        # Look for .env first in backend/, then in project root (../env)
        "env_file": [".env", "../.env"],
        "env_file_encoding": "utf-8",
    }

    def get_temp_dir(self) -> Path:
        if self.temp_dir:
            p = Path(self.temp_dir)
        else:
            p = Path.home() / ".subtitle-generator" / "tmp"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_stt_model(self, quality_mode: str) -> str:
        """Return the appropriate Whisper model for the requested quality mode."""
        if quality_mode == "high_quality":
            return self.groq_stt_quality_model
        return self.groq_stt_fast_model


settings = Settings()
