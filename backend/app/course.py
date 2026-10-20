"""The Direct Instruction course: scripted lessons, soft mastery gates, mastery tests and per-item results.

Lessons live in data/course/NNN.json. Each lesson is a list of short exercises from different tracks.
Things filled in when lessons load, so lesson files stay short:
- distractors: every spoken item is also checked against the other answers in its exercise;
- src: every item records where it was written ([lesson, exercise, item]), so it can be checked wherever it
  is reused (review, tests, remedial lessons);
- review: an exercise with "review": N gets N spoken items from earlier lessons, spaced 1, 2, 3, 5, 8…
  lessons back (cumulative review). When a learner opens a lesson, items they have missed recently take
  up to half of that block (see Course.review_items).
The gates are soft (the learner's choice, 2026-10-20): with only a few items per exercise, a 90% gate
meant one miss failed the round. Finishing a round always moves the lesson on to the next exercise.
A round that reaches PASS_ACCURACY on first tries (corrections and re-tests inside the round don't
count as first tries) is "passed"; below that, the learner may go again, and the items missed come back
in review either way. A lesson is passed (done) when every exercise has had a round, and only then does
the next lesson unlock.

Every UNIT_SIZE lessons make a unit, and a unit ends with a mastery test: one try at a sample of the
unit's items, with no help. Taking it unlocks the next unit, pass or fail. Failing it offers a remedial
lesson built from the items missed, and then the test again (with a new sample that includes those
items), but neither is required: the items missed come back in review anyway. A unit's
test can also be taken before its lessons, to test out of them (placement): passing marks the unit's
lessons as passed, and failing just means starting the unit's lessons.
"""
import json
import math
import random
import time
from functools import lru_cache
from pathlib import Path

from . import config
from .db import connect
from .flashcards import needs_stress_mark
from .text import display_stress, strip_stress

PASS_ACCURACY = 0.9
TEST_PASS_ACCURACY = 0.9
TRACKS = {"script", "frames", "vocab", "listening", "sounds", "numbers", "dialogue", "review"}
TYPES = {"teach", "say", "choose", "dialogue"}
STEPS = {"first", "practice", "retest", "delayed"}  # only "first" tries decide whether a round passes
REVIEW_DISTANCES = (1, 2, 3, 5, 8, 13, 21)  # lessons back that review items are drawn from
MAX_AUTO_DISTRACTORS = 5
UNIT_SIZE = 5
TEST_SPOKEN_PER_LESSON = 3
TEST_CHOSEN_PER_LESSON = 2
REVIEW_ERROR_SHARE = 0.5  # at most this share of a review block goes to items missed recently
REVIEW_CARD_SHARE = 0.34  # and at most this share to lesson words that are due in the flashcards
RECENT_TRIES = 4  # an item's last few counted tries decide whether it counts as "missed recently"
COUNTED_STEPS = ("first", "delayed", "test")  # tries without help just before


class LessonLocked(Exception):
    pass


class NotAvailable(Exception):
    pass


def _describe(text: str) -> dict:
    return {"text": text, "display": display_stress(text), "plain": strip_stress(text)}


def item_key(exercise_type: str, item: dict) -> str:
    """Stable identity of an item across lessons (for delayed tests and review statistics)."""
    if exercise_type == "choose" and "prompt" in item:
        return f"form:{strip_stress(item['prompt']).lower()}={strip_stress(item['options'][item['correct']]).lower()}"
    if exercise_type == "choose":
        return f"hear:{strip_stress(item['audio']).lower()}"
    return f"say:{strip_stress(item['answer']).lower()}"


def spoken_items(lesson: dict) -> list[dict]:
    """Items the learner answers by speaking (teach, say and the learner's dialogue turns)."""
    return [item for ex in lesson["exercises"] if ex["type"] in ("teach", "say", "dialogue")
            for item in ex.get("items", []) if "answer" in item]


def own_items(lesson: dict) -> list[tuple[dict, dict]]:
    """(exercise, item) for the items a lesson teaches itself: everything outside its review exercises."""
    return [(ex, item) for ex in lesson["exercises"] if not ex.get("review") for item in ex["items"]
            if not (ex["type"] == "dialogue" and item.get("speaker") == "partner")]


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
        if not ex.get("items") and not ex.get("review"):
            errors.append(f"{at}: no items")
        if ex.get("review") and ex.get("type") != "say":
            errors.append(f"{at}: review exercises must be type 'say'")
        for i_idx, item in enumerate(ex.get("items", [])):
            it = f"{at} item {i_idx + 1}"
            if ex.get("type") == "choose":
                if not ("audio" in item or "prompt" in item) or not item.get("options"):
                    errors.append(f"{it}: choose items need 'options' and an 'audio' or a 'prompt'")
                elif not 0 <= item.get("correct", -1) < len(item["options"]):
                    errors.append(f"{it}: 'correct' must index into options")
                texts = [item.get("audio", ""), item.get("prompt", "")]
                if "prompt" in item:  # choosing a written form: the options are Russian
                    texts += item.get("options", [])
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


def _with_distractors(ex: dict) -> dict:
    """Check each spoken answer against the other answers in its exercise too (plus any listed)."""
    if ex["type"] not in ("teach", "say", "dialogue") or "items" not in ex:
        return ex
    answers = [i["answer"] for i in ex["items"] if "answer" in i]
    items = []
    for item in ex["items"]:
        if "answer" in item:
            taken = {strip_stress(t).lower() for t in [item["answer"], *item.get("accept", [])]}
            extra = []
            for other in [*item.get("distractors", []), *answers]:
                key = strip_stress(other).lower()
                if key not in taken:
                    taken.add(key)
                    extra.append(other)
            n_listed = len(item.get("distractors", []))
            item = {**item, "distractors": extra[:max(n_listed, MAX_AUTO_DISTRACTORS)]}
        items.append(item)
    return {**ex, "items": items}


def _review_items(earlier: list[dict], lesson: dict, count: int) -> list[dict]:
    """Spoken items from earlier lessons, taken in turn from 1, 2, 3, 5, 8… lessons back."""
    own = {item_key("say", i) for i in spoken_items(lesson)}
    pools = []
    for d in REVIEW_DISTANCES:
        source = next((l for l in earlier if l["id"] == lesson["id"] - d), None)
        if source:
            items = spoken_items(source)
            start = lesson["id"] % len(items) if items else 0  # vary which items come up
            pools.append(items[start:] + items[:start])
    picked, seen = [], set(own)
    while len(picked) < count and any(pools):
        for pool in pools:
            while pool:
                item = pool.pop(0)
                if item_key("say", item) not in seen:
                    seen.add(item_key("say", item))
                    picked.append(item)
                    break
            if len(picked) == count:
                break
    return picked


def load_lessons(directory: Path) -> tuple[dict, ...]:
    """Read, validate and fill in every lesson file in a directory."""
    raw = []
    for path in sorted(directory.glob("[0-9]*.json")):
        lesson = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_lesson(lesson)
        if errors:
            raise ValueError(f"{path.name}: " + "; ".join(errors))
        raw.append(lesson)
    raw.sort(key=lambda l: l["id"])
    done: list[dict] = []
    for lesson in raw:
        exercises = [_with_distractors(ex) for ex in lesson["exercises"]]
        exercises = [{**ex, "items": _review_items(done, lesson, ex["review"])} if ex.get("review") else ex
                     for ex in exercises]
        exercises = [ex for ex in exercises if ex["items"]]
        exercises = [ex if ex.get("review") else
                     {**ex, "items": [{**item, "src": [lesson["id"], e_idx, i_idx]}
                                      for i_idx, item in enumerate(ex["items"])]}
                     for e_idx, ex in enumerate(exercises)]
        done.append({**lesson, "exercises": exercises})
    return tuple(done)


@lru_cache(maxsize=1)
def lessons() -> tuple[dict, ...]:
    """All lessons, in order. Raises ValueError if any lesson file is malformed."""
    return load_lessons(config.DATA_DIR / "course")


def _lesson(lesson_id: int) -> dict:
    for lesson in lessons():
        if lesson["id"] == lesson_id:
            return lesson
    raise KeyError(lesson_id)


def item_at(src: list[int] | tuple[int, int, int]) -> dict:
    """The item written at [lesson, exercise, item]."""
    lesson_id, exercise, item = src
    if exercise < 0 or item < 0:
        raise KeyError(src)
    try:
        return _lesson(lesson_id)["exercises"][exercise]["items"][item]
    except IndexError:
        raise KeyError(src)


# ---------- words ----------

@lru_cache(maxsize=1)
def _introductions() -> dict[str, int]:
    from .curriculum import introductions

    return introductions(lessons())


@lru_cache(maxsize=4096)
def lesson_for(russian: str) -> int | None:
    """The lesson that introduces a single word (any form of it), e.g. a flashcard's word."""
    from .curriculum import word_lemmas

    lemmas = word_lemmas(russian)
    return _introductions().get(lemmas[0]) if len(lemmas) == 1 else None


@lru_cache(maxsize=1024)
def _practice_src(russian: str) -> tuple[int, int, int] | None:
    """Where a word is practised in the lesson that introduces it: its own teach item if it has one,
    otherwise the shortest spoken answer in that lesson that uses it."""
    from .curriculum import word_lemmas

    lesson_id = lesson_for(russian)
    if lesson_id is None:
        return None
    target = word_lemmas(russian)[0]
    found = [(len(word_lemmas(item["answer"])), item["src"]) for ex, item in own_items(_lesson(lesson_id))
             if "answer" in item and target in word_lemmas(item["answer"])]
    return tuple(min(found)[1]) if found else None


# ---------- units ----------

def unit_of(lesson_id: int) -> int:
    return (lesson_id - 1) // UNIT_SIZE + 1


def unit_lessons(unit: int) -> list[dict]:
    return [l for l in lessons() if unit_of(l["id"]) == unit]


def units() -> list[int]:
    """Units with all their lessons written (only those have a mastery test)."""
    out = []
    for lesson in lessons():
        if lesson["id"] % UNIT_SIZE == 0 and len(unit_lessons(unit_of(lesson["id"]))) == UNIT_SIZE:
            out.append(unit_of(lesson["id"]))
    return out


def _unit_items(unit: int) -> dict[str, tuple[dict, dict]]:
    """Every item a unit teaches, by key: (exercise, item)."""
    out = {}
    for lesson in unit_lessons(unit):
        for ex, item in own_items(lesson):
            out.setdefault(item_key("choose" if ex["type"] == "choose" else "say", item), (ex, item))
    return out


def build_test(unit: int, attempt: int, missed: set[str] = frozenset()) -> dict:
    """A mastery test for a unit: a few spoken and a few listening/reading items from each lesson, sentences
    first, always including the items missed last time. The sample is fixed for a given attempt."""
    rng = random.Random(f"test {unit} {attempt}")
    spoken, chosen, seen = [], [], set()
    for lesson in unit_lessons(unit):
        for want, kind, bucket in ((TEST_SPOKEN_PER_LESSON, "say", spoken), (TEST_CHOSEN_PER_LESSON, "choose", chosen)):
            pool = [(ex, item) for ex, item in own_items(lesson)
                    if (ex["type"] == "choose") == (kind == "choose")]
            rng.shuffle(pool)
            pool.sort(key=lambda p: (item_key(kind, p[1]) not in missed, p[0]["track"] not in ("frames", "dialogue")))
            taken = 0
            for ex, item in pool:
                key = item_key(kind, item)
                if key in seen or (taken >= want and key not in missed):
                    continue
                seen.add(key)
                bucket.append(item)
                taken += 1
    rng.shuffle(spoken)
    rng.shuffle(chosen)
    first, last = unit_lessons(unit)[0]["id"], unit_lessons(unit)[-1]["id"]
    exercises = [
        {"track": "review", "type": "say", "title": "Speaking",
         "instruction": "Answer from the picture. No help this time, just do your best.", "items": spoken},
        {"track": "listening", "type": "choose", "title": "Listening and reading",
         "instruction": "Pick the right answer.", "items": chosen},
    ]
    return {"id": unit, "kind": "test", "title": f"Test: lessons {first}–{last}",
            "goal": f"Show that lessons {first}–{last} are solid: one try at each item, no help.",
            "exercises": [ex for ex in exercises if ex["items"]]}


def build_remedial(unit: int, missed: list[str]) -> dict:
    """Re-teach the items missed in a mastery test: spoken ones modelled and led again, the rest re-done."""
    items = _unit_items(unit)
    spoken = [items[k][1] for k in missed if k in items and items[k][0]["type"] != "choose"]
    chosen = [items[k][1] for k in missed if k in items and items[k][0]["type"] == "choose"]
    exercises = []
    for n in range(0, len(spoken), 5):
        exercises.append({"track": "review", "type": "teach", "title": "Let's fix these",
                          "instruction": "These came up in the test. Listen, say it after me, then on your own.",
                          "items": spoken[n:n + 5]})
    if chosen:
        exercises.append({"track": "listening", "type": "choose", "title": "And these",
                          "instruction": "These came up in the test too. Pick the right answer.", "items": chosen})
    first, last = unit_lessons(unit)[0]["id"], unit_lessons(unit)[-1]["id"]
    return {"id": unit, "kind": "remedial", "title": f"Fix-up: lessons {first}–{last}",
            "goal": "Firm up what the test showed wasn't solid yet. Then take the test again.",
            "exercises": exercises}


def _expand(lesson: dict) -> dict:
    """Lesson content as the client needs it: display forms and item keys filled in."""
    exercises = []
    for ex in lesson["exercises"]:
        items = []
        for item in ex["items"]:
            out = dict(item)
            if ex["type"] == "choose":
                for field in ("audio", "prompt"):
                    if field in item:
                        out[field] = _describe(item[field])
                if "prompt" in item:  # written Russian forms to choose from
                    out["options"] = [display_stress(o) for o in item["options"]]
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

    def _tests(self) -> dict[int, list[dict]]:
        """Test attempts per unit, oldest first."""
        with connect(self.path) as conn:
            rows = conn.execute("SELECT * FROM course_tests ORDER BY id").fetchall()
        out: dict[int, list[dict]] = {}
        for r in rows:
            out.setdefault(r["unit"], []).append({**dict(r), "missed": json.loads(r["missed"])})
        return out

    @staticmethod
    def _test_status(unit: int, attempts: list[dict], lesson_status: dict[int, str], prev_done: bool) -> str:
        """passed | remedial (fix-up lesson first) | available (lessons done: test due) | skip (test out) | locked"""
        if any(a["passed"] for a in attempts):
            return "passed"
        if not prev_done:
            return "locked"
        last = attempts[-1] if attempts else None
        if (last and last["kind"] == "mastery" and last["remedial_passed_at"] is None
                and build_remedial(unit, last["missed"])["exercises"]):
            return "remedial"
        if all(lesson_status.get(l["id"]) == "passed" for l in unit_lessons(unit)):
            return "available"
        return "skip"

    def overview(self) -> dict:
        progress = self._progress()
        tests = self._tests()
        unit_ids = set(units())
        out, statuses, unlocked = [], {}, True
        test_out, prev_test_done = [], True
        for lesson in lessons():
            p = progress.get(lesson["id"], {})
            passed = p.get("passed_at") is not None
            status = "passed" if passed else "available" if unlocked else "locked"
            statuses[lesson["id"]] = status
            out.append({"id": lesson["id"], "title": lesson["title"], "goal": lesson["goal"], "status": status,
                        "exercises": len(lesson["exercises"]), "exercise": p.get("exercise", 0),
                        "placed": bool(p.get("placed")), "unit": unit_of(lesson["id"]),
                        "tracks": sorted({e["track"] for e in lesson["exercises"]})})
            unlocked = unlocked and passed
            unit = unit_of(lesson["id"])
            if lesson["id"] % UNIT_SIZE == 0 and unit in unit_ids:
                attempts = tests.get(unit, [])
                t_status = self._test_status(unit, attempts, statuses, prev_test_done)
                first = unit_lessons(unit)[0]["id"]
                taken = any(a["kind"] == "mastery" for a in attempts)
                test_out.append({"unit": unit, "first": first, "last": lesson["id"], "status": t_status,
                                 "attempts": len(attempts), "taken": taken,
                                 "best": max((a["accuracy"] for a in attempts), default=None),
                                 "last_accuracy": attempts[-1]["accuracy"] if attempts else None})
                # soft gate: a mastery test taken, passed or not, opens the next unit
                prev_test_done = t_status == "passed" or taken
                unlocked = unlocked and prev_test_done
        current = next((l["id"] for l in out if l["status"] == "available"), None)
        # a test not taken yet comes next; after a failed one, the fix-up and retake are optional
        due = next((t for t in test_out if t["status"] == "available" and not t["taken"]), None)
        if due and (current is None or current > due["last"]):
            nxt = {"kind": "test", "id": due["unit"]}
        else:
            nxt = {"kind": "lesson", "id": current} if current else None
        started = bool(progress) or bool(tests)
        return {"lessons": out, "tests": test_out, "current": current, "next": nxt, "started": started,
                "pass_accuracy": PASS_ACCURACY, "test_pass_accuracy": TEST_PASS_ACCURACY, "unit_size": UNIT_SIZE}

    def _status(self, lesson_id: int) -> str:
        return next(l["status"] for l in self.overview()["lessons"] if l["id"] == lesson_id)

    def lesson(self, lesson_id: int) -> dict:
        lesson = _lesson(lesson_id)
        status = self._status(lesson_id)
        if status == "locked":
            raise LessonLocked(lesson_id)
        p = self._progress().get(lesson_id, {})
        exercises = [{**ex, "items": self.review_items(lesson, ex["review"], ex["items"])} if ex.get("review") else ex
                     for ex in lesson["exercises"]]
        return {**_expand({**lesson, "exercises": exercises}), "kind": "lesson", "status": status,
                "exercise": p.get("exercise", 0)}

    # ---------- review driven by errors ----------

    def missed_recently(self) -> dict[str, float]:
        """Item key → share of its last few counted tries that were wrong (only items with a miss)."""
        with connect(self.path) as conn:
            rows = conn.execute(
                f"SELECT item_key, correct FROM course_results WHERE step IN ({','.join('?' * len(COUNTED_STEPS))}) "
                "ORDER BY created_at DESC, id DESC", COUNTED_STEPS).fetchall()
        tries: dict[str, list[int]] = {}
        for r in rows:
            got = tries.setdefault(r["item_key"], [])
            if len(got) < RECENT_TRIES:
                got.append(r["correct"])
        return {k: 1 - sum(v) / len(v) for k, v in tries.items() if 0 in v}

    def due_cards(self, before_lesson: int) -> list[dict]:
        """Flashcards that are due, for words taught before a lesson: the item to practise each one with."""
        with connect(self.path) as conn:
            rows = conn.execute("SELECT id, russian FROM cards WHERE suspended = 0 AND reps > 0 AND due <= ? "
                                "ORDER BY due", (time.time(),)).fetchall()
        out, seen = [], set()
        for r in rows:
            lesson_id = lesson_for(r["russian"])
            src = _practice_src(r["russian"]) if lesson_id and lesson_id < before_lesson else None
            if src and src not in seen:
                seen.add(src)
                out.append({**item_at(src), "card": r["id"]})
        return out

    def review_items(self, lesson: dict, count: int, spaced: list[dict]) -> list[dict]:
        """A lesson's review block: items missed recently first (up to REVIEW_ERROR_SHARE of it), then lesson
        words due in the flashcards (up to REVIEW_CARD_SHARE), then the spaced items (1, 2, 3, 5, 8… lessons
        back)."""
        missed = self.missed_recently()
        own = {item_key("say", i) for ex, i in own_items(lesson) if "answer" in i}
        pool: dict[str, dict] = {}
        for earlier in lessons():
            if earlier["id"] >= lesson["id"]:
                break
            for ex, item in own_items(earlier):
                if "answer" in item:
                    pool.setdefault(item_key("say", item), item)
        errors = sorted((k for k in missed if k in pool and k not in own), key=lambda k: -missed[k])
        picked = [pool[k] for k in errors[:math.ceil(count * REVIEW_ERROR_SHARE)]]
        seen = {item_key("say", i) for i in picked} | own
        cards = [c for c in self.due_cards(lesson["id"]) if item_key("say", c) not in seen]
        for item in cards[:math.floor(count * REVIEW_CARD_SHARE)]:
            seen.add(item_key("say", item))
            picked.append(item)
        for item in spaced:
            if len(picked) >= count:
                break
            if item_key("say", item) not in seen:
                seen.add(item_key("say", item))
                picked.append(item)
        return picked

    # ---------- conversation ----------

    def taught(self) -> dict:
        """Words (lemmas) and grammar from the lessons passed so far, for the conversation partner."""
        from .curriculum import introductions

        passed = {l["id"] for l in self.overview()["lessons"] if l["status"] == "passed"}
        done = tuple(l for l in lessons() if l["id"] in passed)
        return {"words": sorted(introductions(done)), "grammar": [f"{l['title']}: {l['goal']}" for l in done],
                "lessons": len(done)}

    # ---------- dashboard ----------

    def stats(self) -> dict:
        """Accuracy per track (first tries and test answers), test history and the items to work on."""
        where: dict[str, tuple[str, dict, str]] = {}  # key -> (track, item, exercise type)
        for lesson in lessons():
            for ex, item in own_items(lesson):
                kind = "choose" if ex["type"] == "choose" else "say"
                where.setdefault(item_key(kind, item), (ex["track"], item, ex["type"]))
        with connect(self.path) as conn:
            rows = conn.execute("SELECT item_key, correct, created_at FROM course_results "
                                "WHERE step IN ('first', 'test') ORDER BY created_at DESC, id DESC").fetchall()
            tests = conn.execute("SELECT unit, kind, accuracy, passed, created_at FROM course_tests "
                                 "ORDER BY id").fetchall()
        tracks: dict[str, dict] = {}
        for r in rows:
            track = where.get(r["item_key"], ("review",))[0]
            t = tracks.setdefault(track, {"track": track, "tries": 0, "right": 0, "recent": []})
            t["tries"] += 1
            t["right"] += r["correct"]
            if len(t["recent"]) < 50:
                t["recent"].append(r["correct"])
        by_track = [{"track": t["track"], "tries": t["tries"], "accuracy": round(t["right"] / t["tries"], 3),
                     "recent_accuracy": round(sum(t["recent"]) / len(t["recent"]), 3)}
                    for t in sorted(tracks.values(), key=lambda t: -t["tries"])]
        work_on = []
        for key, rate in sorted(self.missed_recently().items(), key=lambda kv: -kv[1]):
            if key not in where:
                continue
            track, item, ex_type = where[key]
            text = item.get("answer") or item.get("audio") or item.get("prompt")
            work_on.append({"key": key, "track": track, "miss_rate": round(rate, 2),
                            "display": display_stress(text), "english": item.get("english", ""),
                            "cue": item.get("cue", ""), "src": item["src"]})
            if len(work_on) == 8:
                break
        return {"tracks": by_track, "tests": [dict(t) for t in tests], "work_on": work_on,
                "first_tries": len(rows), "items_seen": len({r["item_key"] for r in rows})}

    # ---------- lessons ----------

    def finish_round(self, lesson_id: int, exercise: int, results: list[dict]) -> dict:
        """Record one round of an exercise. Passing it moves the lesson on to the next exercise."""
        lesson = _lesson(lesson_id)
        if self._status(lesson_id) == "locked":
            raise LessonLocked(lesson_id)
        if not 0 <= exercise < len(lesson["exercises"]):
            raise KeyError(exercise)
        ex = lesson["exercises"][exercise]
        accuracy = _accuracy(ex, results)
        passed = accuracy >= PASS_ACCURACY
        now = time.time()
        self._rate_cards(results)
        with connect(self.path) as conn:
            _save_results(conn, lesson_id, exercise, results, now)
            row = conn.execute("SELECT * FROM course_progress WHERE lesson_id = ?", (lesson_id,)).fetchone()
            current = row["exercise"] if row else 0
            if row is None:
                conn.execute("INSERT INTO course_progress (lesson_id, exercise, started_at) VALUES (?, 0, ?)",
                             (lesson_id, now))
            if exercise >= current:  # soft gate: any finished round moves on
                current = exercise + 1
                done = current >= len(lesson["exercises"])
                conn.execute("UPDATE course_progress SET exercise = ?, passed_at = COALESCE(passed_at, ?) "
                             "WHERE lesson_id = ?", (current, now if done else None, lesson_id))
        overview = self.overview()
        lesson_passed = next(l for l in overview["lessons"] if l["id"] == lesson_id)["status"] == "passed"
        if lesson_passed:
            self._schedule_words([lesson_id])
        return {"passed": passed, "accuracy": round(accuracy, 3), "exercise": current,
                "lesson_passed": lesson_passed, "next_lesson": overview["current"] if lesson_passed else None,
                "next": overview["next"] if lesson_passed else None}

    def _rate_cards(self, results: list[dict]) -> None:
        """A due flashcard answered in a review block counts as its flashcard review: right first time is
        Good, wrong is Again."""
        from .flashcards import FlashcardStore, NotFound

        store = FlashcardStore(self.path)
        for r in results:
            if r.get("card") is not None and r.get("step") == "first":
                try:
                    store.rate(int(r["card"]), 3 if r.get("correct") else 1)
                except NotFound:
                    pass

    def _schedule_words(self, lesson_ids: list[int]) -> None:
        """Words a passed lesson taught join the flashcard schedule (if they're still new there)."""
        from .flashcards import FlashcardStore

        FlashcardStore(self.path).schedule_learned(lambda russian: lesson_for(russian) in lesson_ids)

    def restart(self, lesson_id: int) -> None:
        """Go through a lesson again from the first exercise (a passed lesson stays passed)."""
        if self._status(lesson_id) == "locked":
            raise LessonLocked(lesson_id)
        with connect(self.path) as conn:
            conn.execute("UPDATE course_progress SET exercise = 0 WHERE lesson_id = ?", (lesson_id,))

    # ---------- tests ----------

    def _test_state(self, unit: int) -> tuple[dict, list[dict]]:
        if unit not in units():
            raise KeyError(unit)
        t = next(t for t in self.overview()["tests"] if t["unit"] == unit)
        return t, self._tests().get(unit, [])

    def test(self, unit: int) -> dict:
        state, attempts = self._test_state(unit)
        if state["status"] in ("locked", "remedial"):
            raise NotAvailable(state["status"])
        missed = set(attempts[-1]["missed"]) if attempts else set()
        return {**_expand(build_test(unit, len(attempts), missed)), "status": state["status"],
                "exercise": 0, "attempt": len(attempts) + 1}

    def finish_test(self, unit: int, results: list[dict]) -> dict:
        state, attempts = self._test_state(unit)
        if state["status"] in ("locked", "remedial"):
            raise NotAvailable(state["status"])
        test = build_test(unit, len(attempts), set(attempts[-1]["missed"]) if attempts else set())
        keys = {item_key("choose" if ex["type"] == "choose" else "say", item)
                for ex in test["exercises"] for item in ex["items"]}
        answers = {}
        for r in results:  # one answer per item: the first one sent
            if r.get("key") in keys:
                answers.setdefault(r["key"], r)
        accuracy = sum(bool(r.get("correct")) for r in answers.values()) / len(keys)
        passed = accuracy >= TEST_PASS_ACCURACY
        missed = sorted(k for k in keys if not answers.get(k, {}).get("correct"))
        kind = "mastery" if state["status"] in ("available", "passed") else "placement"
        now = time.time()
        with connect(self.path) as conn:
            _save_results(conn, 0, unit, [{**r, "step": "test"} for r in answers.values()], now)
            conn.execute("INSERT INTO course_tests (unit, kind, accuracy, passed, missed, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (unit, kind, accuracy, int(passed), json.dumps(missed), now))
            if passed:
                for lesson in unit_lessons(unit):
                    n = len(lesson["exercises"])
                    conn.execute(
                        "INSERT INTO course_progress (lesson_id, exercise, started_at, passed_at, placed) "
                        "VALUES (?, ?, ?, ?, 1) ON CONFLICT(lesson_id) DO UPDATE SET "
                        "placed = CASE WHEN passed_at IS NULL THEN 1 ELSE placed END, "
                        "exercise = CASE WHEN passed_at IS NULL THEN excluded.exercise ELSE exercise END, "
                        "passed_at = COALESCE(passed_at, excluded.passed_at)", (lesson["id"], n, now, now))
        if passed:
            self._schedule_words([l["id"] for l in unit_lessons(unit)])
        overview = self.overview()
        next_test = next((t for t in overview["tests"] if t["unit"] == unit + 1 and t["status"] == "skip"), None)
        return {"passed": passed, "accuracy": round(accuracy, 3), "kind": kind, "missed": len(missed),
                "total": len(keys), "remedial": not passed and kind == "mastery" and state["status"] != "passed",
                "next": overview["next"], "next_test": next_test["unit"] if next_test and kind == "placement" else None}

    def remedial(self, unit: int) -> dict:
        state, attempts = self._test_state(unit)
        if state["status"] != "remedial":
            raise NotAvailable(state["status"])
        last = attempts[-1]
        lesson = build_remedial(unit, last["missed"])
        return {**_expand(lesson), "status": "available", "exercise": last["remedial_exercise"]}

    def finish_remedial_round(self, unit: int, exercise: int, results: list[dict]) -> dict:
        state, attempts = self._test_state(unit)
        if state["status"] != "remedial":
            raise NotAvailable(state["status"])
        last = attempts[-1]
        lesson = build_remedial(unit, last["missed"])
        if not 0 <= exercise < len(lesson["exercises"]):
            raise KeyError(exercise)
        accuracy = _accuracy(lesson["exercises"][exercise], results)
        passed = accuracy >= PASS_ACCURACY
        current = last["remedial_exercise"]
        now = time.time()
        self._rate_cards(results)
        with connect(self.path) as conn:
            _save_results(conn, 0, unit, results, now)
            if exercise >= current:
                current = exercise + 1
                done = current >= len(lesson["exercises"])
                conn.execute("UPDATE course_tests SET remedial_exercise = ?, remedial_passed_at = ? WHERE id = ?",
                             (current, now if done else None, last["id"]))
        done = current >= len(lesson["exercises"])
        return {"passed": passed, "accuracy": round(accuracy, 3), "exercise": current, "lesson_passed": done,
                "next_lesson": None, "next": {"kind": "test", "id": unit} if done else None}

    def can_check(self, src: list[int], test_unit: int | None) -> bool:
        """May the learner be checked on the item at src? Yes in unlocked lessons, and in a test they may take."""
        if self._status(src[0]) != "locked":
            return True
        if test_unit is None or unit_of(src[0]) != test_unit or test_unit not in units():
            return False
        state, _ = self._test_state(test_unit)
        return state["status"] in ("available", "skip", "passed")


def _accuracy(ex: dict, results: list[dict]) -> float:
    firsts = [r for r in results if r.get("step") == "first"]
    if ex["type"] == "dialogue" and not firsts:
        return 1.0  # nothing was required of the learner
    return sum(bool(r.get("correct")) for r in firsts) / len(firsts) if firsts else 0.0


def _save_results(conn, lesson_id: int, exercise: int, results: list[dict], now: float) -> None:
    conn.executemany(
        """INSERT INTO course_results (lesson_id, exercise, item_key, step, correct, override, score, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(lesson_id, exercise, str(r.get("key", ""))[:200],
          r.get("step") if r.get("step") in STEPS | {"test"} else "first",
          int(bool(r.get("correct"))), int(bool(r.get("override"))), r.get("score"), now) for r in results])


course = Course()
