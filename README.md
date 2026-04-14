# Subtitle Generator

Desktop application for generating multilingual subtitles from local video files.

## Features

- Import local videos (MP4, MOV, MKV, AVI, WEBM)
- Analyze video metadata and audio tracks
- Select audio track when multiple are present
- Automatic speech-to-text transcription with timestamps
- Export subtitles as `.srt` and `.vtt`
- Translate subtitles to multiple languages (FR, EN, ES, DE)
- Chunking support for large audio files
- Partial failure resilience (failed translations don't block successful exports)

## Architecture

- **Frontend**: React + TypeScript (Tauri desktop shell)
- **Backend**: Python + FastAPI (local API)
- **Media processing**: ffmpeg / ffprobe
- **AI providers**: Groq (configurable via provider pattern)

## Prerequisites

### System dependencies

**ffmpeg and ffprobe** must be installed and available in PATH.

macOS:
```bash
brew install ffmpeg
```

Ubuntu/Debian:
```bash
sudo apt install ffmpeg
```

Verify installation:
```bash
ffmpeg -version
ffprobe -version
```

### Python 3.11+

```bash
python3 --version
```

### Node.js 18+

```bash
node --version
```

### Rust (for Tauri build only)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

## Setup

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 2. Start the backend

```bash
./scripts/run_backend.sh
```

This creates a Python virtualenv, installs dependencies, and starts the API on `http://127.0.0.1:8000`.

### 3. Start the frontend (dev mode)

```bash
./scripts/run_frontend.sh
```

This installs npm dependencies and starts Vite dev server on `http://localhost:1420` with API proxy to the backend.

### 4. Run as Tauri desktop app (optional)

```bash
cd apps/desktop
npm run tauri dev
```

## Running tests

```bash
./scripts/run_tests.sh
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/videos/probe` | Analyze video metadata |
| POST | `/api/jobs` | Create a subtitle generation job |
| GET | `/api/jobs/{id}` | Get job status |
| GET | `/api/jobs/{id}/preview` | Preview subtitle segments |
| GET | `/api/jobs/{id}/downloads` | List export files |
| GET | `/api/jobs/{id}/downloads/{file}` | Download an export file |
| DELETE | `/api/jobs/{id}` | Delete job and cleanup |

## Project structure

```
subtitle-generator/
  apps/desktop/            # React + TypeScript + Tauri frontend
    src/
      components/          # UI components
      hooks/               # Custom React hooks
      services/            # API client
      types/               # TypeScript type definitions
    src-tauri/             # Tauri desktop shell (Rust)
  backend/
    app/
      api/                 # FastAPI routes
      core/                # Config, logging
      models/              # Pydantic schemas
      services/
        media/             # Probe, extraction, chunking
        stt/               # Speech-to-text orchestration
        translation/       # Translation orchestration
        subtitles/         # Post-processing, export
        jobs/              # Job manager
      providers/           # Provider interfaces + Groq implementation
      utils/               # Timestamps, filesystem utilities
    tests/                 # Backend tests
  scripts/                 # Run scripts
```

## Export naming convention

- `video.original.srt` / `video.original.vtt` — source language
- `video.fr.srt` / `video.fr.vtt` — French
- `video.en.srt` / `video.en.vtt` — English
- `video.es.srt` / `video.es.vtt` — Spanish
- `video.de.srt` / `video.de.vtt` — German

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key (required) | — |
| `GROQ_TRANSCRIPTION_MODEL` | Whisper model for STT | `whisper-large-v3` |
| `GROQ_TRANSLATION_MODEL` | LLM model for translation | `llama-3.3-70b-versatile` |
| `MAX_UPLOAD_MB` | Max video file size | `2048` |
| `MAX_API_AUDIO_CHUNK_MB` | Max chunk size for API | `25` |
| `TEMP_DIR` | Temp files directory | `~/.subtitle-generator/tmp` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DEBUG_KEEP_TEMP_FILES` | Keep temp files for debugging | `false` |
