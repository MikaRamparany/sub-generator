from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, set_job_manager
from app.core.config import settings
from app.core.logging import logger
from app.providers.deepl_translation import DeepLTranslationProvider
from app.providers.groq_stt import GroqSTTProvider
from app.providers.groq_translation import GroqTranslationProvider
from app.services.jobs.job_manager import JobManager
from app.services.media.extraction_service import check_ffmpeg_available
from app.services.media.probe_service import check_ffprobe_available

app = FastAPI(title="Subtitle Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Translation: prefer DeepL if configured (no TPM issues), fall back to Groq LLM
stt_provider = GroqSTTProvider()
if settings.deepl_api_key:
    translation_provider = DeepLTranslationProvider()
    logger.info("Translation provider: DeepL")
else:
    translation_provider = GroqTranslationProvider()
    logger.info("Translation provider: Groq LLM (set DEEPL_API_KEY to use DeepL)")

job_manager = JobManager(stt_provider, translation_provider)
set_job_manager(job_manager)

app.include_router(router)


@app.on_event("startup")
async def startup_checks():
    if not check_ffmpeg_available():
        logger.warning("ffmpeg not found in PATH - media processing will fail")
    if not check_ffprobe_available():
        logger.warning("ffprobe not found in PATH - video probing will fail")
    logger.info("Subtitle Generator API started")
