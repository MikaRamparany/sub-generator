from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import (
    ExportFile,
    JobConfig,
    JobStatus,
    SubtitleSegment,
    TranslatedSubtitleSegment,
)
from app.providers.base import SpeechToTextProvider, SubtitleTranslationProvider
from app.services.media.chunking_service import AudioChunk, chunk_audio, needs_chunking
from app.services.media.extraction_service import extract_audio
from app.services.subtitles.export_service import (
    segments_to_srt,
    segments_to_vtt,
    translated_segments_to_subtitle_segments,
    write_subtitle_file,
)
from app.services.subtitles.postprocess_service import clean_segments
from app.utils.filesystem import (
    cleanup_directory,
    ensure_dir,
    get_export_filename,
)


class Job:
    def __init__(self, job_id: str, config: JobConfig):
        self.job_id = job_id
        self.config = config
        self.status = JobStatus(job_id=job_id, state="idle", progress=0.0)
        self.source_segments: list[SubtitleSegment] = []
        self.translations: dict[str, list[TranslatedSubtitleSegment]] = {}
        self.export_files: list[ExportFile] = []
        # work_dir holds all intermediates; export_dir is kept until delete
        self.work_dir = ensure_dir(settings.get_temp_dir() / job_id)
        self.export_dir = ensure_dir(self.work_dir / "exports")

    def update(self, state: str, progress: float, message: str = "") -> None:
        self.status.state = state
        self.status.progress = progress
        self.status.message = message
        logger.info(f"[Job {self.job_id}] {state} ({progress:.0%}) {message}")

    def fail(self, message: str, error_code: str | None = None) -> None:
        self.status.state = "failed"
        self.status.message = message
        self.status.error_code = error_code
        logger.error(f"[Job {self.job_id}] FAILED: {message}")

    def record_translation_failure(self, lang: str, reason: str) -> None:
        """Record a partial translation failure without overwriting other state."""
        self.status.failed_languages.append(lang)
        logger.warning(f"[Job {self.job_id}] Translation to '{lang}' failed: {reason}")


class JobManager:
    def __init__(
        self,
        stt_provider: SpeechToTextProvider,
        translation_provider: SubtitleTranslationProvider,
    ):
        self.stt_provider = stt_provider
        self.translation_provider = translation_provider
        self.jobs: dict[str, Job] = {}

    def create_job(self, config: JobConfig) -> str:
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id, config)
        self.jobs[job_id] = job
        logger.info(f"Created job {job_id} for {config.input_video_path}")
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete job and clean up ALL files (including exports)."""
        job = self.jobs.pop(job_id, None)
        if job:
            cleanup_directory(job.work_dir)
            return True
        return False

    async def run_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return

        config = job.config
        audio_path: str | None = None
        chunk_dir: Path | None = None

        try:
            # Step 1: Extract audio
            job.update("extracting_audio", 0.1, "Extracting audio from video...")
            audio_path = str(job.work_dir / "audio.wav")
            extract_audio(config.input_video_path, audio_path, config.audio_track_index)

            # Step 2: Chunking if needed
            chunks: list[AudioChunk] = []
            if needs_chunking(audio_path):
                job.update("chunking_audio", 0.2, "Audio too large, splitting into chunks...")
                chunk_dir = ensure_dir(job.work_dir / "chunks")
                chunks = chunk_audio(audio_path, str(chunk_dir))
            else:
                chunks = [AudioChunk(path=audio_path, offset_seconds=0.0)]

            # Step 3: Transcribe
            job.update("transcribing", 0.3, "Transcribing audio...")
            all_segments: list[SubtitleSegment] = []
            total_chunks = len(chunks)

            for i, chunk in enumerate(chunks):
                progress = 0.3 + (0.3 * (i / total_chunks))
                job.update("transcribing", progress, f"Transcribing chunk {i + 1}/{total_chunks}...")

                source_lang = config.source_language if config.source_language != "auto" else None
                segments = await self.stt_provider.transcribe(
                    chunk.path,
                    source_language=source_lang,
                    quality_mode=config.quality_mode,
                )

                # Apply time offset for chunked audio
                if chunk.offset_seconds > 0:
                    segments = [
                        SubtitleSegment(
                            id=s.id,
                            start=s.start + chunk.offset_seconds,
                            end=s.end + chunk.offset_seconds,
                            text=s.text,
                        )
                        for s in segments
                    ]
                all_segments.extend(segments)

            if not all_segments:
                job.fail("Transcription produced no segments", "empty_transcription")
                return

            # Step 4: Post-process
            job.update("post_processing", 0.65, "Cleaning up segments...")
            job.source_segments = clean_segments(all_segments)

            # Step 5: Generate source exports
            self._generate_exports(job, job.source_segments, "original")

            # Cleanup intermediates now that exports are generated
            # (chunks + raw audio) — keeps only the export_dir
            self._cleanup_intermediates(audio_path, chunk_dir)

            # Step 6: Translate
            if config.target_languages:
                job.update("translating", 0.7, "Translating subtitles...")
                total_langs = len(config.target_languages)

                for i, lang in enumerate(config.target_languages):
                    progress = 0.7 + (0.25 * (i / total_langs))
                    job.update("translating", progress, f"Translating to {lang}...")

                    try:
                        translated = await self.translation_provider.translate_segments(
                            job.source_segments,
                            target_language=lang,
                            source_language=config.source_language if config.source_language != "auto" else None,
                        )
                        job.translations[lang] = translated
                        translated_as_segments = translated_segments_to_subtitle_segments(translated)
                        self._generate_exports(job, translated_as_segments, lang)

                    except Exception as e:
                        job.record_translation_failure(lang, str(e))

            # Finalize with accurate summary message
            failed = job.status.failed_languages
            if failed:
                langs_str = ", ".join(failed)
                job.update(
                    "completed",
                    1.0,
                    f"Done with partial results — translation failed for: {langs_str}.",
                )
            else:
                job.update("completed", 1.0, "All subtitles generated successfully.")

        except Exception as e:
            # Try to cleanup intermediates even on hard failure
            if audio_path:
                self._cleanup_intermediates(audio_path, chunk_dir)
            msg = str(e) or f"{type(e).__name__} (no details)"
            job.fail(msg, "pipeline_error")

    def _generate_exports(
        self, job: Job, segments: list[SubtitleSegment], language: str
    ) -> None:
        for fmt in job.config.output_formats:
            filename = get_export_filename(job.config.input_video_path, language, fmt)
            output_path = str(job.export_dir / filename)

            if fmt == "srt":
                content = segments_to_srt(segments)
            elif fmt == "vtt":
                content = segments_to_vtt(segments)
            else:
                continue

            write_subtitle_file(content, output_path)
            job.export_files.append(
                ExportFile(
                    file_name=filename,
                    language=language,
                    format=fmt,
                    file_path=output_path,
                )
            )

    def _cleanup_intermediates(
        self, audio_path: str | None, chunk_dir: Path | None
    ) -> None:
        """Remove intermediate audio files, keep only export_dir."""
        if settings.debug_keep_temp_files:
            return
        if audio_path:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Could not remove audio file: {e}")
        if chunk_dir and chunk_dir.exists():
            try:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not remove chunk dir: {e}")
