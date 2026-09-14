import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = BACKEND_DIR / "models"
CACHE_DIR = BACKEND_DIR / "cache"
TTS_CACHE_DIR = CACHE_DIR / "tts"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

# Whisper model (mlx-community repos). "whisper-small-mlx" uses less RAM; turbo is more accurate.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")

# Russian letter-level CTC model used for pronunciation scoring
PRONUNCIATION_MODEL = os.environ.get("PRONUNCIATION_MODEL", "bond005/wav2vec2-large-ru-golos")

# Silero TTS (Russian). Speakers: aidar, baya, kseniya, xenia, eugene
SILERO_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
SILERO_PATH = MODELS_DIR / "silero_v4_ru.pt"
TTS_SPEAKER = os.environ.get("TTS_SPEAKER", "xenia")
TTS_SAMPLE_RATE = 48000

for d in (MODELS_DIR, TTS_CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
