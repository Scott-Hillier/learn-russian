"""Direct Instruction course: lesson files, soft gates and round scoring (no speech models needed)."""
import pytest
from fastapi.testclient import TestClient

from app.course import Course, LessonLocked, _expand, item_at, item_key, lessons, validate_lesson


@pytest.fixture
def course(tmp_path):
    return Course(tmp_path / "progress.db")


def _pass_all(course, lesson):
    for i, ex in enumerate(lesson["exercises"]):
        results = [{"key": f"k{j}", "step": "first", "correct": True} for j, _ in enumerate(ex["items"])]
        out = course.finish_round(lesson["id"], i, results)
        assert out["passed"]
    return out


def test_lesson_files_are_valid_and_in_order():
    found = lessons()
    assert [l["id"] for l in found] == list(range(1, len(found) + 1))
    for lesson in found:
        assert validate_lesson(lesson) == []
        assert len({e["track"] for e in lesson["exercises"]}) >= 3, f"lesson {lesson['id']} needs 3+ tracks"


def test_validation_catches_missing_stress_and_bad_choice():
    lesson = {"id": 9, "title": "t", "goal": "g", "exercises": [
        {"track": "vocab", "type": "say", "title": "x", "instruction": "",
         "items": [{"answer": "собака", "cue": "🐕"}]},
        {"track": "listening", "type": "choose", "title": "x", "instruction": "",
         "items": [{"audio": "дом", "options": ["🏠"], "correct": 3}]},
    ]}
    errors = validate_lesson(lesson)
    assert any("'собака' has no stress mark" in e for e in errors)
    assert any("'correct' must index into options" in e for e in errors)


def test_one_noun_answers_also_accept_the_this_is_frame():
    lesson = _expand(lessons()[0])
    dog = next(i for i in lesson["exercises"][0]["items"] if i["answer"]["plain"] == "собака")
    spec = item_at(dog["src"])
    assert "+Это соб+ака." in spec["accept"]
    # framed wrong answers compete with the framed right one, so «Это кошка.» can't pass as «Это собака.»
    assert {"к+ошка", "+Это к+ошка."} <= set(spec["distractors"])
    assert not any("Это" in a for a in item_at([1, 3, 0]).get("accept", []))  # sentences stay as written
    numbers = next(e for e in lessons()[0]["exercises"] if e["track"] == "numbers")
    assert not any(i.get("accept") for i in numbers["items"])


def test_picture_options_are_labelled_in_english():
    choose = next(e for e in _expand(lessons()[0])["exercises"] if e["type"] == "choose")
    item = choose["items"][0]
    assert dict(zip(item["options"], item["labels"])) == {"🏠": "house", "🐱": "cat", "🐶": "dog"}


def test_item_keys_ignore_stress_marks():
    assert item_key("say", {"answer": "+Это к+ошка."}) == "say:это кошка."
    assert item_key("choose", {"audio": "К+ошка там."}) == "hear:кошка там."


def test_only_the_first_lesson_starts_unlocked(course):
    statuses = [l["status"] for l in course.overview()["lessons"]]
    assert statuses[0] == "available" and set(statuses[1:]) == {"locked"}
    with pytest.raises(LessonLocked):
        course.lesson(2)
    with pytest.raises(LessonLocked):
        course.finish_round(2, 0, [])


def test_round_passes_at_ninety_percent_of_first_tries_but_moves_on_either_way(course):
    first = lessons()[0]
    n = len(first["exercises"][0]["items"])
    misses = [{"key": "a", "step": "first", "correct": False}] + \
             [{"key": f"k{i}", "step": "first", "correct": True} for i in range(n - 1)]
    out = course.finish_round(1, 0, misses + [{"key": "a", "step": "retest", "correct": True}])
    assert not out["passed"] and out["exercise"] == 1  # soft gate
    # going again over an exercise already done doesn't move the lesson back
    out = course.finish_round(1, 0, misses)
    assert out["exercise"] == 1
    # practice and re-test steps don't count either way
    ok = [{"key": f"k{i}", "step": "first", "correct": True} for i in range(n)] + \
         [{"key": "x", "step": "practice", "correct": False}]
    out = course.finish_round(1, 1, ok)
    assert out["passed"] and out["exercise"] == 2 and not out["lesson_passed"]


def test_a_lesson_with_failed_rounds_still_unlocks_the_next(course):
    for i, _ in enumerate(lessons()[0]["exercises"]):
        out = course.finish_round(1, i, [{"key": "a", "step": "first", "correct": False}])
    assert not out["passed"] and out["lesson_passed"] and out["next_lesson"] == 2
    assert course.lesson(2)["status"] == "available"


def test_overridden_answers_count_as_right(course):
    out = course.finish_round(1, 0, [{"key": "a", "step": "first", "correct": True, "override": True}])
    assert out["passed"]


def test_passing_every_exercise_unlocks_the_next_lesson(course):
    out = _pass_all(course, lessons()[0])
    assert out["lesson_passed"] and out["next_lesson"] == 2
    assert course.lesson(2)["status"] == "available"
    # practising a passed lesson again keeps it passed
    course.restart(1)
    assert course.lesson(1)["status"] == "passed" and course.lesson(1)["exercise"] == 0


def test_course_api(tmp_path, monkeypatch):
    from app import routes_course
    from app.main import app

    monkeypatch.setattr(routes_course, "course", Course(tmp_path / "progress.db"))
    client = TestClient(app)
    body = client.get("/api/course").json()
    assert body["current"] == 1 and body["lessons"][0]["status"] == "available"
    lesson = client.get("/api/course/1").json()
    assert lesson["exercises"][0]["items"][0]["answer"]["display"]
    assert all("key" in i for i in lesson["exercises"][0]["items"])
    assert client.get("/api/course/2").status_code == 403
    assert client.get("/api/course/999").status_code == 404
    r = client.post("/api/course/1/rounds", json={"exercise": 0, "results": [
        {"key": "say:дом", "step": "first", "correct": True}]})
    assert r.status_code == 200 and r.json()["passed"]
    r = client.post("/api/course/1/check", data={"exercise": "1", "item": "0"},
                    files={"audio": ("a.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 400  # listening items aren't answered by speaking


def test_check_reports_silence_without_scoring(tmp_path, monkeypatch):
    from app import routes_course
    from app.main import app
    from tests.test_api import _silent_wav

    monkeypatch.setattr(routes_course, "course", Course(tmp_path / "progress.db"))
    r = TestClient(app).post("/api/course/1/check", data={"exercise": "0", "item": "0"},
                             files={"audio": ("a.wav", _silent_wav(), "audio/wav")})
    assert r.status_code == 200 and r.json()["silent"] is True
    assert TestClient(app).post("/api/course/1/check", data={"exercise": "-1", "item": "0"},
                                files={"audio": ("a.wav", _silent_wav(), "audio/wav")}).status_code == 404


def test_lesson_answers_are_saved_with_their_item_when_recording(tmp_path, monkeypatch):
    import json

    import numpy as np

    from app import config, routes_course
    from app.main import app

    monkeypatch.setattr(routes_course, "course", Course(tmp_path / "progress.db"))
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    monkeypatch.setattr(config, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr(routes_course, "decode_to_pcm16k", lambda data: np.full(16000, 0.1, dtype=np.float32))
    monkeypatch.setattr(routes_course, "check_answer", lambda *a: {
        "correct": True, "silent": False, "heard": None, "score": 90, "words": []})
    r = TestClient(app).post("/api/course/1/check", data={"exercise": "0", "item": "0"},
                             files={"audio": ("a.webm", b"audio", "audio/webm")})
    assert r.status_code == 200
    saved = json.loads(next((tmp_path / "recordings").glob("*.json")).read_text())
    assert saved["target"] == "дом" and saved["feedback"]["lesson"] == 1 and "distractors" in saved["feedback"]


def test_a_check_from_an_out_of_date_page_is_refused(tmp_path, monkeypatch):
    """A page from before items carried their src sent [lesson, exercise, position]. In a review block that
    position named a different item from the one on screen (🐶 shown, «Это дом.» checked)."""
    from app import routes_course
    from app.main import app

    monkeypatch.setattr(routes_course, "course", Course(tmp_path / "progress.db"))
    client = TestClient(app)
    audio = {"audio": ("a.wav", b"RIFF", "audio/wav")}
    review = next(i for i, e in enumerate(lessons()[1]["exercises"]) if e.get("review"))
    r = client.post("/api/course/2/check", data={"exercise": str(review), "item": "0"}, files=audio)
    assert r.status_code == 409 and "Reload" in r.json()["detail"]
    dog = item_at([1, 0, 2])
    r = client.post("/api/course/1/check", data={"exercise": "0", "item": "0", "key": item_key("say", dog)},
                    files=audio)
    assert r.status_code == 409
    # the right key gets through to the audio check
    r = client.post("/api/course/1/check", data={"exercise": "0", "item": "2", "key": item_key("say", dog)},
                    files=audio)
    assert r.status_code == 400  # b"RIFF" isn't audio


def test_health_names_the_current_ui_bundle():
    from app.main import _bundle

    from app import config
    if (config.FRONTEND_DIST / "index.html").exists():
        assert _bundle().startswith("/assets/") and _bundle().endswith(".js")
