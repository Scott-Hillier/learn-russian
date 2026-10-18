"""The Direct Instruction course: scripted lessons, hard mastery gates and per-item results.

Lessons live in data/course/*.json. Each lesson is a list of short exercises from different tracks.
An exercise is passed when one round of it reaches PASS_ACCURACY on first tries (corrections and
re-tests inside the round don't count as first tries). A lesson is passed when all of its exercises
are, and only then does the next lesson unlock.
"""
import json
import time
from functools import lru_cache
from pathlib import Path

from . import config
from .db import connect
from .flashcards import needs_stress_mark
from .text import display_stress, strip_stress

PASS_ACCURACY = 0.9
TRACKS = {"script", "frames", "vocab", "listening", "sounds", "numbers", "dialogue", "review"}
TYPES = {"teach", "say", "choose", "dialogue"}
STEPS = {"first", "practice", "retest", "delayed"}  # only "first" tries decide whether a round passes


class LessonLocked(Exception):
    pass


def _describe(text: str) -> dict:
    return {"text": text, "display": display_stress(text), "plain": strip_stress(text)}


def item_key(exercise_type: str, item: dict) -> str:
    """Stable identity of an item across lessons (for delayed tests and review statistics)."""
    if exercise_type == "choose":
        return f"hear:{strip_stress(item['audio']).lower()}"
    return f"say:{strip_stress(item['answer']).lower()}"


def validate_lesson(lesson: dict) -> list[str]:
    """Problems with a lesson file (empty list when it's fine)."""
    errors = []
    where = f"lesson {lesson.get('id')}"
    for field in ("id", "title", "goal", "exercises"):
        if field not in lesson:
            errors.append(f"{where}: missing '{field}'")
    for e_idx, ex in enumerate(lesson.get("exercises", [])):
        at = f"{where} exercise {e_idx + 1}"
        if ex.get("track") not in TRACKS:
            errors.append(f"{at}: unknown track {ex.get('track')!r}")
        if ex.get("type") not in TYPES:
            errors.append(f"{at}: unknown type {ex.get('type')!r}")
        if not ex.get("items"):
            errors.append(f"{at}: no items")
        for i_idx, item in enumerate(ex.get("items", [])):
            it = f"{at} item {i_idx + 1}"
            if ex.get("type") == "choose":
                if "audio" not in item or not item.get("options"):
                    errors.append(f"{it}: choose items need 'audio' and 'options'")
                elif not 0 <= item.get("correct", -1) < len(item["options"]):
                    errors.append(f"{it}: 'correct' must index into options")
                texts = [item.get("audio", "")]
            elif ex.get("type") == "dialogue" and item.get("speaker") == "partner":
                if "line" not in item:
                    errors.append(f"{it}: partner turns need 'line'")
                texts = [item.get("line", "")]
            else:
                if "answer" not in item:
                    errors.append(f"{it}: missing 'answer'")
                if not (item.get("cue") or item.get("english")):
                    errors.append(f"{it}: needs a 'cue' or 'english' prompt")
                texts = [item.get("answer", ""), *item.get("accept", []), *item.get("distractors", [])]
            for text in texts:
                for word in strip_punct(text).split():
                    if needs_stress_mark(word):
                        errors.append(f"{it}: '{word}' has no stress mark")
    return errors


def strip_punct(text: str) -> str:
    return "".join(c if c.isalpha() or c in "+- " else " " for c in text)


@lru_cache(maxsize=1)
def lessons() -> tuple[dict, ...]:
    """All lessons, in order. Raises ValueError if any lesson file is malformed."""
    found = []
    for path in sorted((config.DATA_DIR / "course").glob("*.json")):
        lesson = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_lesson(lesson)
        if errors:
            raise ValueError(f"{path.name}: " + "; ".join(errors))
        found.append(lesson)
    found.sort(key=lambda l: l["id"])
    return tuple(found)


def _lesson(lesson_id: int) -> dict:
    for lesson in lessons():
        if lesson["id"] == lesson_id:
            return lesson
    raise KeyError(lesson_id)


def _expand(lesson: dict) -> dict:
    """Lesson content as the client needs it: display forms and item keys filled in."""
    exercises = []
    for ex in lesson["exercises"]:
        items = []
        for item in ex["items"]:
            out = dict(item)
            if ex["type"] == "choose":
                out["audio"] = _describe(item["audio"])
            elif ex["type"] == "dialogue" and item.get("speaker") == "partner":
                out["line"] = _describe(item["line"])
            else:
                out["answer"] = _describe(item["answer"])
                if "ask" in item:
                    out["ask"] = _describe(item["ask"])
            if not (ex["type"] == "dialogue" and item.get("speaker") == "partner"):
                out["key"] = item_key("choose" if ex["type"] == "choose" else "say", item)
            items.append(out)
        exercises.append({**ex, "items": items})
    return {**lesson, "exercises": exercises}


class Course:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def _progress(self) -> dict[int, dict]:
        with connect(self.path) as conn:
            rows = conn.execute("SELECT * FROM course_progress").fetchall()
        return {r["lesson_id"]: dict(r) for r in rows}

    def overview(self) -> dict:
        progress = self._progress()
        out, unlocked = [], True
        for lesson in lessons():
            p = progress.get(lesson["id"], {})
            passed = p.get("passed_at") is not None
            status = "passed" if passed else "available" if unlocked else "locked"
            out.append({"id": lesson["id"], "title": lesson["title"], "goal": lesson["goal"], "status": status,
                        "exercises": len(lesson["exercises"]), "exercise": p.get("exercise", 0),
                        "tracks": sorted({e["track"] for e in lesson["exercises"]})})
            unlocked = unlocked and passed
        current = next((l["id"] for l in out if l["status"] == "available"), None)
        return {"lessons": out, "current": current, "pass_accuracy": PASS_ACCURACY}

    def _status(self, lesson_id: int) -> str:
        return next(l["status"] for l in self.overview()["lessons"] if l["id"] == lesson_id)

    def lesson(self, lesson_id: int) -> dict:
        lesson = _lesson(lesson_id)
        status = self._status(lesson_id)
        if status == "locked":
            raise LessonLocked(lesson_id)
        p = self._progress().get(lesson_id, {})
        return {**_expand(lesson), "status": status, "exercise": p.get("exercise", 0)}

    def finish_round(self, lesson_id: int, exercise: int, results: list[dict]) -> dict:
        """Record one round of an exercise. Passing it moves the lesson on to the next exercise."""
        lesson = _lesson(lesson_id)
        if self._status(lesson_id) == "locked":
            raise LessonLocked(lesson_id)
        if not 0 <= exercise < len(lesson["exercises"]):
            raise KeyError(exercise)
        ex = lesson["exercises"][exercise]
        firsts = [r for r in results if r.get("step") == "first"]
        if ex["type"] == "dialogue" and not firsts:
            accuracy = 1.0  # nothing was required of the learner
        else:
            accuracy = sum(bool(r.get("correct")) for r in firsts) / len(firsts) if firsts else 0.0
        passed = accuracy >= PASS_ACCURACY
        now = time.time()
        with connect(self.path) as conn:
            conn.executemany(
                """INSERT INTO course_results (lesson_id, exercise, item_key, step, correct, override, score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(lesson_id, exercise, str(r.get("key", ""))[:200], r.get("step") if r.get("step") in STEPS else "first",
                  int(bool(r.get("correct"))), int(bool(r.get("override"))), r.get("score"), now) for r in results])
            row = conn.execute("SELECT * FROM course_progress WHERE lesson_id = ?", (lesson_id,)).fetchone()
            current = row["exercise"] if row else 0
            if row is None:
                conn.execute("INSERT INTO course_progress (lesson_id, exercise, started_at) VALUES (?, 0, ?)",
                             (lesson_id, now))
            if passed and exercise >= current:
                current = exercise + 1
                done = current >= len(lesson["exercises"])
                conn.execute("UPDATE course_progress SET exercise = ?, passed_at = COALESCE(passed_at, ?) "
                             "WHERE lesson_id = ?", (current, now if done else None, lesson_id))
        overview = self.overview()
        lesson_passed = next(l for l in overview["lessons"] if l["id"] == lesson_id)["status"] == "passed"
        return {"passed": passed, "accuracy": round(accuracy, 3), "exercise": current,
                "lesson_passed": lesson_passed, "next_lesson": overview["current"] if lesson_passed else None}

    def restart(self, lesson_id: int) -> None:
        """Go through a lesson again from the first exercise (a passed lesson stays passed)."""
        if self._status(lesson_id) == "locked":
            raise LessonLocked(lesson_id)
        with connect(self.path) as conn:
            conn.execute("UPDATE course_progress SET exercise = 0 WHERE lesson_id = ?", (lesson_id,))


course = Course()
