import asyncio
import json
import logging
import threading

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .speech.asr import asr
from .speech.audio import decode_to_pcm16k, peak_level, trim_and_pad
from .speech.compare import build_feedback
from .speech.pronunciation import scorer
from .speech.tts import tts
from .text import display_stress, strip_stress, target_words, transliterate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("learn-russian")

app = FastAPI(title="Learn Russian")


def _describe(text: str) -> dict:
    return {"text": text, "display": display_stress(text), "plain": strip_stress(text),
            "translit": transliterate(text)}


def _load_phrases() -> list[dict]:
    phrases = json.loads((config.DATA_DIR / "phrases.json").read_text(encoding="utf-8"))
    return [{"id": i, **p, **_describe(p["text"])} for i, p in enumerate(phrases)]


PHRASES = _load_phrases()


@app.on_event("startup")
def _warm_up() -> None:
    def run():
        try:
            tts.load()
            asr.warm_up()
            scorer.load()
            log.info("Models ready (TTS: %s, ASR: %s, pronunciation: %s)",
                     tts.engine, config.WHISPER_MODEL, config.PRONUNCIATION_MODEL)
        except Exception:
            log.exception("Model warm-up failed")
    threading.Thread(target=run, daemon=True).start()


@app.get("/api/health")
def health():
    return {"tts": tts.engine, "asr_loaded": asr.loaded, "asr_model": config.WHISPER_MODEL,
            "pronunciation_loaded": scorer.loaded, "ready": asr.loaded and scorer.loaded}


@app.get("/api/phrases")
def phrases():
    return PHRASES


@app.get("/api/describe")
def describe(text: str = Query(..., max_length=500)):
    return _describe(text)


@app.get("/api/tts")
def speak(text: str = Query(..., max_length=500), speed: str = "normal"):
    try:
        path = tts.synthesize(text, speed)
    except Exception as e:
        log.exception("TTS failed")
        raise HTTPException(500, f"Speech synthesis failed: {e}")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "max-age=86400"})


def _score_pronunciation(words: list[str], pcm) -> list[dict] | None:
    try:
        return scorer.score(words, pcm)
    except Exception:
        log.exception("Pronunciation scoring failed; falling back to word recognition only")
        return None


@app.post("/api/attempt")
async def attempt(target: str = Form(..., max_length=500), audio: UploadFile = File(...)):
    words = target_words(target)
    if not words:
        raise HTTPException(400, "Target text has no Russian words.")
    data = await audio.read()
    try:
        pcm = decode_to_pcm16k(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if pcm.size < 16000 * 0.2 or peak_level(pcm) < 0.02:
        return build_feedback(target, "", None)
    pcm = trim_and_pad(pcm)
    heard, pronunciation = await asyncio.gather(
        asyncio.to_thread(asr.transcribe, pcm),
        asyncio.to_thread(_score_pronunciation, words, pcm),
    )
    return build_feedback(target, heard, pronunciation)


if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
