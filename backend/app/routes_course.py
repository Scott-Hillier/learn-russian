import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import config, progress, recordings
from .course import LessonLocked, NotAvailable, _lesson, course, item_at, item_key
from .speech.answers import check_answer
from .speech.audio import decode_to_pcm16k, peak_level, trim_and_pad

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/course")

OUT_OF_DATE = "This page is out of date: the app was updated. Reload the page (⌘R) and carry on."


class ResultIn(BaseModel):
    key: str = Field(max_length=200)
    step: str = Field(max_length=20)
    correct: bool
    override: bool = False
    score: int | None = Field(None, ge=0, le=100)
    card: int | None = None  # a due flashcard practised in a review block


class RoundIn(BaseModel):
    exercise: int
    results: list[ResultIn] = Field(max_length=500)


class TestIn(BaseModel):
    results: list[ResultIn] = Field(max_length=500)


def _call(fn, *args):
    try:
        return fn(*args)
    except LessonLocked:
        raise HTTPException(403, "This lesson is locked. Pass the lesson before it first.")
    except NotAvailable as e:
        message = {"locked": "Pass the test before this one first.",
                   "remedial": "Do the fix-up lesson first, then take the test again."}.get(str(e), "Not available now.")
        raise HTTPException(403, message)
    except KeyError:
        raise HTTPException(404, "No such lesson, test or exercise.")


@router.get("")
def overview():
    return course.overview()


@router.get("/stats")
def stats():
    return course.stats()


@router.get("/tests/{unit}")
def test(unit: int):
    return _call(course.test, unit)


@router.post("/tests/{unit}/finish")
def finish_test(unit: int, body: TestIn):
    return _call(course.finish_test, unit, [r.model_dump() for r in body.results])


@router.get("/tests/{unit}/remedial")
def remedial(unit: int):
    return _call(course.remedial, unit)


@router.post("/tests/{unit}/remedial/rounds")
def finish_remedial_round(unit: int, body: RoundIn):
    return _call(course.finish_remedial_round, unit, body.exercise, [r.model_dump() for r in body.results])


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
async def check(lesson_id: int, exercise: int = Form(...), item: int = Form(...), test: int | None = Form(None),
                key: str | None = Form(None), audio: UploadFile = File(...)):
    """Is the spoken answer to an item right? Scored against the item's answer and its likely wrong answers.

    The item is the one written at lesson / exercise / item (its "src"), wherever it is being practised. Items
    in locked lessons can only be checked while taking that unit's test (`test`). `key` is the item key the
    page shows: if it isn't the item at src, the page is out of date and nothing is checked.
    """
    src = [lesson_id, exercise, item]
    try:
        spec = item_at(src)
    except KeyError:
        raise HTTPException(404, "No such item.")
    # A review block is put together per learner, so a position in one never names an item. Only a page from
    # before items carried their src sends one, and checking it would score the wrong answer.
    if _lesson(lesson_id)["exercises"][exercise].get("review") or (key and key != item_key("say", spec)):
        raise HTTPException(409, OUT_OF_DATE)
    if not course.can_check(src, test):
        raise HTTPException(403, "This lesson is locked. Pass the lesson before it first.")
    if "answer" not in spec:
        raise HTTPException(400, "This item isn't answered by speaking.")
    data = await audio.read()
    try:
        pcm = decode_to_pcm16k(data)
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
    if config.SAVE_RECORDINGS:  # keep the lesson context so a misjudged answer can be replayed against its item
        context = {**result, "lesson": lesson_id, "exercise": exercise, "item": item,
                   "accept": spec.get("accept", []), "distractors": spec.get("distractors", [])}
        await asyncio.to_thread(recordings.save, spec["answer"], data, context)
    return result
