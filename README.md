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
- **Backend**: Python + FastAPI (local API on `http://127.0.0.1:8000`)
- **Media processing**: ffmpeg / ffprobe
- **AI providers**: Groq (configurable via provider pattern)

---

## Prerequisites

### System dependencies

**ffmpeg and ffprobe** must be installed and in PATH.

macOS:
```bash
brew install ffmpeg
```

Ubuntu/Debian:
```bash
sudo apt install ffmpeg
```

Verify:
```bash
ffmpeg -version
ffprobe -version
```

If ffmpeg or ffprobe are absent, the backend will return a clear error on probe/extraction.

---

### Python 3.9+

All backend files use `from __future__ import annotations` — Python 3.9 is the minimum confirmed working version (tested with 3.9.6).

```bash
python3 --version
```

---

### Node.js 18+

```bash
node --version
```

---

### Rust (required for `tauri dev` / `tauri build`)

Rust is required to compile the Tauri desktop shell. Without it, only the browser dev mode works.

Install Rust:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
```

Verify:
```bash
rustc --version
cargo --version
```

---

## Setup

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set GROQ_API_KEY
```

### 2. Start the backend

```bash
./scripts/run_backend.sh
```

Creates a Python virtualenv, installs dependencies, starts the FastAPI server on `http://127.0.0.1:8000`.

### 3a. Run as Tauri desktop app (requires Rust)

```bash
cd apps/desktop
npm install
npm run tauri dev
```

This compiles the Tauri shell and opens the native desktop window.

### 3b. Run frontend in browser (no Rust needed)

```bash
cd apps/desktop
npm install
npm run dev
```

Opens `http://localhost:1420`. File import will show a browser-mode warning — video paths are not accessible without Tauri. Use this mode to work on UI only.

---

## Running tests

```bash
./scripts/run_tests.sh
```

Or individually:

```bash
# Backend (34 tests)
cd backend && source venv/bin/activate && python -m pytest tests/ -v

# Frontend (18 tests)
cd apps/desktop && npx vitest run
```

---

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key (required) | — |
| `GROQ_STT_FAST_MODEL` | Whisper model for **fast** mode | `whisper-large-v3-turbo` |
| `GROQ_STT_QUALITY_MODEL` | Whisper model for **high_quality** mode | `whisper-large-v3` |
| `GROQ_TRANSLATION_MODEL` | LLM model for translation | `llama-3.3-70b-versatile` |
| `MAX_UPLOAD_MB` | Max video file size | `2048` |
| `MAX_API_AUDIO_CHUNK_MB` | Max audio chunk size for API | `25` |
| `TEMP_DIR` | Temp files directory | `~/.subtitle-generator/tmp` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DEBUG_KEEP_TEMP_FILES` | Keep intermediate files for debugging | `false` |

**STT quality modes:**
- `fast` → uses `GROQ_STT_FAST_MODEL` with default temperature
- `high_quality` → uses `GROQ_STT_QUALITY_MODEL` with `temperature=0` (deterministic)

Set both to the same model if your Groq plan only has one available.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/videos/probe` | Analyze video metadata |
| POST | `/api/jobs` | Create a subtitle generation job |
| GET | `/api/jobs/{id}` | Get job status |
| GET | `/api/jobs/{id}/preview` | Preview subtitle segments |
| GET | `/api/jobs/{id}/downloads` | List export files |
| GET | `/api/jobs/{id}/downloads/{file}` | Download an export file |
| DELETE | `/api/jobs/{id}` | Delete job and clean up all files |

---

## Project structure

```
subtitle-generator/
  apps/desktop/            # React + TypeScript + Tauri frontend
    src/
      components/          # UI components
      hooks/               # Custom React hooks
      lib/                 # tauri.ts — environment detection, file dialog
      services/            # API client
      tests/               # Vitest frontend tests
      types/               # TypeScript type definitions
    src-tauri/             # Tauri shell (Rust) — plugin-dialog registered
  backend/
    app/
      api/                 # FastAPI routes
      core/                # Config, logging
      models/              # Pydantic schemas
      services/
        media/             # Probe, extraction, chunking
        subtitles/         # Post-processing, SRT/VTT export
        jobs/              # Job manager (async pipeline)
      providers/           # SpeechToTextProvider + SubtitleTranslationProvider interfaces
                           # + Groq implementations
      utils/               # Timestamps, filesystem helpers
    tests/                 # 34 pytest tests
  scripts/                 # run_backend.sh / run_frontend.sh / run_tests.sh
  .env.example
```

## Export naming convention

- `video.original.srt` / `video.original.vtt` — source language
- `video.fr.srt` / `video.fr.vtt` — French
- `video.en.srt` / `video.en.vtt` — English
- `video.es.srt` / `video.es.vtt` — Spanish
- `video.de.srt` / `video.de.vtt` — German

## Cleanup strategy

- **Intermediate files** (raw audio, chunks): deleted automatically after transcription completes.
- **Export files** (.srt/.vtt): kept in `~/.subtitle-generator/tmp/{jobId}/exports/` until the job is deleted via `DELETE /api/jobs/{id}`.
- Set `DEBUG_KEEP_TEMP_FILES=true` to skip all automatic cleanup.
