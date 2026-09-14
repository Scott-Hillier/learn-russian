#!/usr/bin/env bash
# Start the Learn Russian app: sets up dependencies on first run, builds the UI, serves on localhost.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
PYTHON="${PYTHON:-python3}"

command -v ffmpeg >/dev/null || { echo "ffmpeg is required: brew install ffmpeg"; exit 1; }

if [ ! -x backend/.venv/bin/python ]; then
  echo "→ Creating Python environment…"
  "$PYTHON" -m venv backend/.venv
fi
if [ ! -f backend/.venv/.installed ] || [ backend/requirements.txt -nt backend/.venv/.installed ]; then
  echo "→ Installing Python packages (first run downloads torch; this takes a few minutes)…"
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt
  touch backend/.venv/.installed
fi

if [ ! -d frontend/node_modules ]; then
  echo "→ Installing frontend packages…"
  (cd frontend && npm install --no-audit --no-fund)
fi
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html 2>/dev/null)" ]; then
  echo "→ Building frontend…"
  (cd frontend && npm run build >/dev/null)
fi

# Conversation partner: local LLM via Ollama (optional; the rest of the app works without it).
CHAT_MODEL="${CHAT_MODEL:-gemma3:4b}"
if command -v ollama >/dev/null; then
  if ! curl -sf http://127.0.0.1:11434/api/version >/dev/null; then
    echo "→ Starting Ollama…"
    mkdir -p backend/userdata
    OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 nohup ollama serve > backend/userdata/ollama.log 2>&1 &
    for _ in $(seq 20); do curl -sf http://127.0.0.1:11434/api/version >/dev/null && break; sleep 0.5; done
  fi
  if ! ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$CHAT_MODEL"; then
    echo "→ Downloading conversation model $CHAT_MODEL (one-time, about 3 GB)…"
    ollama pull "$CHAT_MODEL" || echo "  (download failed; the Conversation screen will show setup steps)"
  fi
else
  echo "→ Ollama not found: the Conversation screen needs it (brew install ollama). Everything else works."
fi

URL="http://localhost:$PORT"
(
  for _ in $(seq 60); do
    if curl -sf "$URL/api/health" >/dev/null; then open "$URL"; break; fi
    sleep 1
  done
) &

echo "→ Starting server at $URL (Ctrl+C to stop)"
cd backend
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
