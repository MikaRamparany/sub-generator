from __future__ import annotations

import asyncio
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
from app.services.subtitles.parse_service import parse_subtitle_file
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
        source = config.input_subtitle_path or config.input_video_path
        logger.info(f"Created job {job_id} for {source}")
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

        if config.input_subtitle_path:
            await self._run_subtitle_import_job(job)
        else:
            await self._run_video_job(job)

    async def _run_subtitle_import_job(self, job: Job) -> None:
        """Pipeline for imported subtitle files: parse → export → translate."""
        config = job.config

        try:
            # Step 1: Parse subtitle file
            job.update("parsing_subtitles", 0.2, "Parsing subtitle file...")
            raw_segments = parse_subtitle_file(config.input_subtitle_path)

            if not raw_segments:
                job.fail("Subtitle file contains no segments", "empty_subtitles")
                return

            # Step 2: Light cleanup (no hallucination/dedup since it's user-provided)
            job.update("post_processing", 0.4, "Processing segments...")
            job.source_segments = raw_segments

            # Step 3: Generate source exports
            self._generate_exports(job, job.source_segments, "original")

            # Step 4: Translate
            await self._translate_phase(job, start_progress=0.5)

            # Finalize
            self._finalize(job)

        except Exception as e:
            msg = str(e) or f"{type(e).__name__} (no details)"
            job.fail(msg, "pipeline_error")

    async def _run_video_job(self, job: Job) -> None:
        """Pipeline for video files: extract → transcribe → export → translate."""
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
            job.status.removed_segment_count = len(all_segments) - len(job.source_segments)

            # Step 5: Generate source exports
            self._generate_exports(job, job.source_segments, "original")

            # Cleanup intermediates now that exports are generated
            self._cleanup_intermediates(audio_path, chunk_dir)

            # Step 6: Translate
            await self._translate_phase(job, start_progress=0.7)

            # Finalize
            self._finalize(job)

        except Exception as e:
            if audio_path:
                self._cleanup_intermediates(audio_path, chunk_dir)
            msg = str(e) or f"{type(e).__name__} (no details)"
            job.fail(msg, "pipeline_error")

    async def _translate_phase(self, job: Job, start_progress: float) -> None:
        """Run translation for all target languages."""
        config = job.config
        if not config.target_languages:
            return

        # Cooldown to let Groq rate limits reset after STT
        job.update("translating", start_progress, "Waiting before translation (rate limit cooldown)...")
        await asyncio.sleep(5)

        total_langs = len(config.target_languages)
        for i, lang in enumerate(config.target_languages):
            progress = start_progress + ((1.0 - start_progress - 0.05) * (i / total_langs))
            job.update("translating", progress, f"Translating to {lang}...")

            try:
                translated = await self.translation_provider.translate_segments(
                    job.source_segments,
                    target_language=lang,
                    source_language=config.source_language if config.source_language != "auto" else None,
                    translation_mode=config.translation_mode,
                )
                job.translations[lang] = translated
                # Count segments where translation fell back to source text
                fallbacks = sum(
                    1 for s in translated if s.translated_text == s.source_text
                )
                job.status.fallback_segment_count += fallbacks
                if fallbacks:
                    logger.warning(
                        f"[Job {job.job_id}] {fallbacks} segments used source text as "
                        f"fallback for lang={lang}"
                    )
                translated_as_segments = translated_segments_to_subtitle_segments(translated)
                self._generate_exports(job, translated_as_segments, lang)

            except Exception as e:
                job.record_translation_failure(lang, str(e))

    def _finalize(self, job: Job) -> None:
        """Set final completed state with an honest summary message."""
        warnings: list[str] = []

        if job.status.failed_languages:
            langs_str = ", ".join(job.status.failed_languages)
            warnings.append(f"translation failed for: {langs_str}")

        if job.status.fallback_segment_count:
            warnings.append(
                f"{job.status.fallback_segment_count} segment(s) kept in source language (rate limit)"
            )

        if job.status.removed_segment_count:
            warnings.append(
                f"{job.status.removed_segment_count} segment(s) removed (hallucinations/annotations)"
            )

        if warnings:
            msg = "Done with warnings — " + "; ".join(warnings) + "."
            job.update("completed", 1.0, msg)
        else:
            job.update("completed", 1.0, "All subtitles generated successfully.")

    def _generate_exports(
        self, job: Job, segments: list[SubtitleSegment], language: str
    ) -> None:
        source_path = job.config.input_subtitle_path or job.config.input_video_path
        for fmt in job.config.output_formats:
            filename = get_export_filename(source_path, language, fmt)
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
