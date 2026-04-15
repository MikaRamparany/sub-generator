from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.core.logging import logger
from app.models.schemas import (
    DownloadListResponse,
    ExportFilePublic,
    JobConfig,
    JobStatus,
    PreviewResponse,
    ProbeRequest,
    ProbeResult,
    SubtitleFileInfo,
)
from app.services.jobs.job_manager import JobManager
from app.services.media.probe_service import probe_video
from app.services.subtitles.parse_service import parse_subtitle_file
from app.utils.filesystem import get_video_base_name, validate_video_path

router = APIRouter(prefix="/api")

_job_manager: JobManager | None = None


def set_job_manager(jm: JobManager) -> None:
    global _job_manager
    _job_manager = jm


def get_job_manager() -> JobManager:
    if _job_manager is None:
        raise RuntimeError("JobManager not initialized")
    return _job_manager


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/videos/probe", response_model=ProbeResult)
async def probe(request: ProbeRequest):
    try:
        validate_video_path(request.video_path)
        result = probe_video(request.video_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subtitles/probe", response_model=SubtitleFileInfo)
async def probe_subtitle(request: ProbeRequest):
    """Probe a subtitle file (SRT/VTT) and return its metadata."""
    file_path = request.video_path  # reuse ProbeRequest — field is just a path
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    ext = path.suffix.lower()
    if ext not in (".srt", ".vtt"):
        raise HTTPException(status_code=400, detail=f"Not a subtitle file: {ext}")
    try:
        segments = parse_subtitle_file(file_path)
        return SubtitleFileInfo(
            file_name=path.name,
            file_size_mb=path.stat().st_size / (1024 * 1024),
            segment_count=len(segments),
            format=ext.lstrip("."),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs")
async def create_job(config: JobConfig, background_tasks: BackgroundTasks):
    is_subtitle_import = bool(config.input_subtitle_path)
    is_video_import = bool(config.input_video_path)

    if not is_subtitle_import and not is_video_import:
        raise HTTPException(
            status_code=400,
            detail="Either input_video_path or input_subtitle_path must be provided",
        )

    if is_video_import and not is_subtitle_import:
        try:
            validate_video_path(config.input_video_path)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    if is_subtitle_import:
        path = Path(config.input_subtitle_path)
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {config.input_subtitle_path}")

    jm = get_job_manager()
    job_id = jm.create_job(config)
    background_tasks.add_task(jm.run_job, job_id)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    jm = get_job_manager()
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.status


@router.get("/jobs/{job_id}/preview", response_model=PreviewResponse)
async def get_job_preview(job_id: str):
    jm = get_job_manager()
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return PreviewResponse(
        source_segments=job.source_segments,
        translations=job.translations,
    )


@router.get("/jobs/{job_id}/downloads", response_model=DownloadListResponse)
async def get_job_downloads(job_id: str):
    jm = get_job_manager()
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    public_files = [
        ExportFilePublic(file_name=f.file_name, language=f.language, format=f.format)
        for f in job.export_files
    ]
    return DownloadListResponse(files=public_files)


# NOTE: this route MUST be declared before /downloads/{file_name}
# so that "zip" is not captured as a file_name parameter.
@router.get("/jobs/{job_id}/downloads/zip")
async def download_zip(job_id: str):
    """Stream all export files for a job as a single zip archive."""
    jm = get_job_manager()
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    available = [f for f in job.export_files if Path(f.file_path).exists()]
    if not available:
        raise HTTPException(status_code=404, detail="No export files available")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for export in available:
            zf.write(export.file_path, arcname=export.file_name)

    buf.seek(0)
    source_path = job.config.input_subtitle_path or job.config.input_video_path
    base_name = get_video_base_name(source_path)
    zip_name = f"{base_name}.subtitles.zip"

    logger.info(f"[Job {job_id}] Serving zip: {zip_name} ({len(available)} files)")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.get("/jobs/{job_id}/downloads/{file_name}")
async def download_file(job_id: str, file_name: str):
    jm = get_job_manager()
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for export in job.export_files:
        if export.file_name == file_name:
            file_path = Path(export.file_path)
            if file_path.exists():
                return FileResponse(
                    path=str(file_path),
                    filename=export.file_name,
                    media_type="application/octet-stream",
                )
            raise HTTPException(status_code=404, detail="File no longer exists on disk")

    raise HTTPException(status_code=404, detail="File not found in job exports")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    jm = get_job_manager()
    if jm.delete_job(job_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Job not found")
