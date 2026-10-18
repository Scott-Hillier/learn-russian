import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import progress
from .course import LessonLocked, course, lessons
from .speech.answers import check_answer
from .speech.audio import decode_to_pcm16k, peak_level, trim_and_pad

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/course")


class ResultIn(BaseModel):
    key: str = Field(max_length=200)
    step: str = Field(max_length=20)
    correct: bool
    override: bool = False
    score: int | None = Field(None, ge=0, le=100)


class RoundIn(BaseModel):
    exercise: int
    results: list[ResultIn] = Field(max_length=500)


def _call(fn, *args):
    try:
        return fn(*args)
    except LessonLocked:
        raise HTTPException(403, "This lesson is locked. Pass the lesson before it first.")
    except KeyError:
        raise HTTPException(404, "No such lesson or exercise.")


@router.get("")
def overview():
    return course.overview()


@router.get("/{lesson_id}")
def lesson(lesson_id: int):
    return _call(course.lesson, lesson_id)


@router.post("/{lesson_id}/rounds")
def finish_round(lesson_id: int, body: RoundIn):
    return _call(course.finish_round, lesson_id, body.exercise, [r.model_dump() for r in body.results])


@router.post("/{lesson_id}/restart")
def restart(lesson_id: int):
    _call(course.restart, lesson_id)
    return {"ok": True}


@router.post("/{lesson_id}/check")
async def check(lesson_id: int, exercise: int = Form(...), item: int = Form(...), audio: UploadFile = File(...)):
    """Is the spoken answer to this item right? Scored against the item's answer and its likely wrong answers."""
    _call(course.lesson, lesson_id)  # enforces the lock
    try:
        if exercise < 0 or item < 0:
            raise IndexError
        spec = next(l for l in lessons() if l["id"] == lesson_id)["exercises"][exercise]["items"][item]
    except (IndexError, StopIteration):
        raise HTTPException(404, "No such item.")
    if "answer" not in spec:
        raise HTTPException(400, "This item isn't answered by speaking.")
    try:
        pcm = decode_to_pcm16k(await audio.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    if pcm.size < 16000 * 0.2 or peak_level(pcm) < 0.02:
        return {"correct": False, "silent": True, "heard": None, "score": 0, "words": []}
    result = await asyncio.to_thread(check_answer, spec["answer"], spec.get("accept", []),
                                     spec.get("distractors", []), trim_and_pad(pcm))
    try:
        progress.record_attempt("lesson", spec["answer"], result)
    except Exception:
        log.exception("Could not save attempt to progress database")
    return result
