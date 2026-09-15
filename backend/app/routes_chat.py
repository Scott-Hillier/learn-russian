import asyncio
import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import chat, config
from .speech.asr import asr
from .speech.audio import decode_to_pcm16k, peak_level, trim_and_pad
from .speech.compare import build_feedback
from .speech.pronunciation import scorer
from .text import display_stress, expand_numbers, strip_stress, target_words, transliterate

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat")


def _load_scenarios() -> dict[str, dict]:
    data = json.loads((config.DATA_DIR / "scenarios.json").read_text(encoding="utf-8"))
    out = {}
    for s in data["scenarios"]:
        def describe(t: str) -> dict:
            t = expand_numbers(t)
            return {"text": t, "display": display_stress(t), "plain": strip_stress(t),
                    "translit": transliterate(t)}

        out[s["id"]] = {**s, "opening": {**s["opening"], **describe(s["opening"]["text"])},
                        "phrases": [{**p, **describe(p["text"])} for p in s["phrases"]]}
    return out


SCENARIOS = _load_scenarios()


class Turn(BaseModel):
    role: str = Field(pattern="^(partner|learner)$")
    text: str = Field(max_length=500)


class ReplyIn(BaseModel):
    scenario_id: str
    history: list[Turn] = Field(max_length=200)
    level: str = "beginner"


class CheckIn(BaseModel):
    text: str = Field(max_length=300)


def _scenario(scenario_id: str) -> dict:
    if scenario_id not in SCENARIOS:
        raise HTTPException(404, "Unknown scenario.")
    return SCENARIOS[scenario_id]


@router.get("/status")
def status():
    return chat.status()


@router.get("/scenarios")
def scenarios():
    return list(SCENARIOS.values())


@router.post("/reply")
async def reply(body: ReplyIn):
    scenario = _scenario(body.scenario_id)
    history = [{"role": t.role, "text": strip_stress(t.text)} for t in body.history]
    try:
        return await asyncio.to_thread(chat.reply, scenario, history, body.level)
    except chat.ChatUnavailable as e:
        raise HTTPException(503, str(e))


@router.post("/check")
async def check(body: CheckIn):
    try:
        return await asyncio.to_thread(chat.check, body.text)
    except chat.ChatUnavailable as e:
        raise HTTPException(503, str(e))


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcribe free speech, plus a clarity score: letters checked against what was recognised.

    Clarity is only a rough guide (it can't know what you *meant* to say), so it isn't saved to the
    per-letter statistics.
    """
    try:
        pcm = decode_to_pcm16k(await audio.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    if pcm.size < 16000 * 0.2 or peak_level(pcm) < 0.02:
        return {"text": "", "clarity": None}
    pcm = trim_and_pad(pcm)
    # Whisper writes spoken numbers as digits ("мне 25 лет"), which the letter-level scorer can't
    # see — spell them back out so the clarity score covers everything that was said.
    text = expand_numbers(await asyncio.to_thread(asr.transcribe, pcm))
    words = target_words(text)
    if not text or not any(chat.CYRILLIC.search(w) for w in words):
        return {"text": text, "clarity": None}
    try:
        pronunciation = await asyncio.to_thread(scorer.score, words, pcm)
    except Exception:
        log.exception("Clarity scoring failed")
        return {"text": text, "clarity": None}
    return {"text": text, "clarity": build_feedback(text, text, pronunciation)}
