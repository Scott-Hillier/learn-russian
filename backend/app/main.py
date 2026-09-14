import asyncio
from contextlib import asynccontextmanager
import json
import logging
import re
import threading

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, progress
from .flashcards import store as flashcards
from .routes_flashcards import router as flashcard_router
from .speech.asr import asr
from .speech.audio import decode_to_pcm16k, peak_level, trim_and_pad, voiced_duration
from .speech.compare import build_feedback
from .speech.pronunciation import scorer
from .speech.tts import tts
from .text import display_stress, strip_stress, target_words, transliterate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("learn-russian")


def _warm_up_models() -> None:
    try:
        tts.load()
        asr.warm_up()
        scorer.load()
        log.info("Models ready (TTS: %s, ASR: %s, pronunciation: %s)",
                 tts.engine, config.WHISPER_MODEL, config.PRONUNCIATION_MODEL)
    except Exception:
        log.exception("Model warm-up failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_up_models, daemon=True).start()  # load speech models in the background
    yield


app = FastAPI(title="Learn Russian", lifespan=lifespan)


def _describe(text: str) -> dict:
    return {"text": text, "display": display_stress(text), "plain": strip_stress(text),
            "translit": transliterate(text)}


def _load_phrases() -> list[dict]:
    phrases = json.loads((config.DATA_DIR / "phrases.json").read_text(encoding="utf-8"))
    return [{"id": i, **p, **_describe(p["text"])} for i, p in enumerate(phrases)]


PHRASES = _load_phrases()


def _load_alphabet() -> dict:
    data = json.loads((config.DATA_DIR / "alphabet.json").read_text(encoding="utf-8"))
    for letter in data["letters"]:
        letter["name_display"] = display_stress(letter["name"])
        letter["examples"] = [{**ex, **_describe(ex["text"])} for ex in letter["examples"]]
        letter["syllables"] = [_describe(s) for s in letter["syllables"]]
    for lesson in data["lessons"]:
        lesson["words"] = [{**w, **_describe(w["text"])} for w in lesson["words"]]
    return data


ALPHABET = _load_alphabet()


def _load_sentences() -> list[dict]:
    data = json.loads((config.DATA_DIR / "sentences.json").read_text(encoding="utf-8"))
    out = []
    for theme in data["themes"]:
        for s in theme["sentences"]:
            text = " ".join(s["text"].replace("|", " ").split())
            words = target_words(text)
            out.append({
                "id": len(out), "theme": theme["title"], "english": s["english"], **_describe(text),
                "chunks": [_describe(c.strip()) for c in s["text"].split("|")],
                "words": [{**_describe(w), "gloss": g} for w, g in zip(words, s["glosses"])],
            })
    return out


SENTENCES = _load_sentences()


def _load_minimal_pairs() -> list[dict]:
    data = json.loads((config.DATA_DIR / "minimal_pairs.json").read_text(encoding="utf-8"))
    for group in data["groups"]:
        group["pairs"] = [{"a": {**_describe(p["a"][0]), "english": p["a"][1]},
                           "b": {**_describe(p["b"][0]), "english": p["b"][1]},
                           "speak": p.get("speak", True)} for p in group["pairs"]]
    return data["groups"]


MINIMAL_PAIRS = _load_minimal_pairs()
SOURCES = {"phrase", "letter", "reading", "custom", "flashcard", "sentence", "pair"}
flashcards.sync_builtin_decks(PHRASES)
app.include_router(flashcard_router)


@app.get("/api/health")
def health():
    return {"tts": tts.engine, "asr_loaded": asr.loaded, "asr_model": config.WHISPER_MODEL,
            "pronunciation_loaded": scorer.loaded, "ready": asr.loaded and scorer.loaded}


@app.get("/api/phrases")
def phrases():
    return PHRASES


@app.get("/api/alphabet")
def alphabet():
    return ALPHABET


@app.get("/api/progress/letters")
def letters_progress():
    return progress.letter_mastery()


@app.get("/api/progress/best")
def best_scores(source: str):
    return progress.best_scores(source)


@app.get("/api/sentences")
def sentences():
    return SENTENCES


@app.get("/api/minimal-pairs")
def minimal_pairs():
    """Groups ordered weakest first: practised sounds scoring below 85%, then by base priority."""
    mastery = progress.letter_mastery()
    groups = []
    for g in MINIMAL_PAIRS:
        stats = [mastery[l] for l in g["letters"] if l in mastery]
        average = min(s["average"] for s in stats) if stats else None
        groups.append({**g, "your_average": average})
    weak = sorted((g for g in groups if g["your_average"] is not None and g["your_average"] < 0.85),
                  key=lambda g: g["your_average"])
    rest = sorted((g for g in groups if g not in weak), key=lambda g: g["priority"])
    return [{**g, "recommended": g in weak} for g in weak + rest]


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


def _timing(target: str, pcm) -> dict | None:
    """Compare the learner's speaking duration with the native (normal speed) voice."""
    try:
        native = voiced_duration(decode_to_pcm16k(tts.synthesize(target, "normal").read_bytes()))
    except Exception:
        log.exception("Could not measure native timing")
        return None
    yours = voiced_duration(pcm)
    if native <= 0 or yours <= 0:
        return None
    return {"yours": round(yours, 2), "native": round(native, 2), "ratio": round(yours / native, 2)}


@app.post("/api/attempt")
async def attempt(target: str = Form(..., max_length=500), audio: UploadFile = File(...),
                  source: str = Form("phrase"), timing: bool = Form(False)):
    words = target_words(target)
    if not any(re.search("[а-яё]", w.lower()) for w in words):
        raise HTTPException(400, "Target text has no Russian words.")
    data = await audio.read()
    try:
        pcm = decode_to_pcm16k(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if pcm.size < 16000 * 0.2 or peak_level(pcm) < 0.02:
        return build_feedback(target, "", None)
    raw_pcm, pcm = pcm, trim_and_pad(pcm)
    heard, pronunciation = await asyncio.gather(
        asyncio.to_thread(asr.transcribe, pcm),
        asyncio.to_thread(_score_pronunciation, words, pcm),
    )
    feedback = build_feedback(target, heard, pronunciation)
    if timing:
        feedback["timing"] = await asyncio.to_thread(_timing, target, raw_pcm)
    if pronunciation is not None:
        try:
            progress.record_attempt(source if source in SOURCES else "phrase", target, feedback)
        except Exception:
            log.exception("Could not save attempt to progress database")
    return feedback


if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
