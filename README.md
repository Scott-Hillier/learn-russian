# Говори́! Learn Russian by speaking

A local, offline speaking partner. Hear a phrase, say it back, and see which words were
understood. See [PLAN.md](PLAN.md) for the roadmap.

## Run
```bash
./start.sh
```
Your browser opens at http://localhost:8000. The first run installs packages and downloads
the speech models (about 1.7 GB). After that the app works fully offline.

Requirements: macOS on Apple Silicon, Python 3.10+, Node 18+, `ffmpeg` (`brew install ffmpeg`).

## How to practise
1. Pick a phrase in the sidebar, or type your own. Mark stress with `+`, e.g. `мол+око`.
2. **🔊 Listen** (`L`) or **🐢 Slow** (`S`).
3. **🎙 Say it** (`Space`). Recording stops when you pause.
4. Words turn green (recognised), amber (almost), red (wrong) or grey-dashed (not heard).
   Compare **My recording** with **Native**.

## Configuration (environment variables)
| Variable | Default | Notes |
|---|---|---|
| `WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | `mlx-community/whisper-small-mlx` uses less RAM |
| `TTS_SPEAKER` | `xenia` | Silero voices: `aidar`, `baya`, `kseniya`, `xenia`, `eugene` |
| `PORT` | `8000` | |

## Development
```bash
cd backend && .venv/bin/python -m pytest -q          # tests
cd backend && .venv/bin/uvicorn app.main:app --reload  # API on :8000
cd frontend && npm run dev                            # UI on :5173 with hot reload
```

The Silero TTS model is licensed CC BY-NC 4.0 (fine for personal use).
