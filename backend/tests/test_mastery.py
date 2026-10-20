"""Mastery tests, remedial lessons, placement and error-driven review (Phase 11). No speech models needed."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.course import (Course, LessonLocked, NotAvailable, UNIT_SIZE, build_test, item_at, item_key, lessons,
                        unit_lessons, units)


@pytest.fixture
def course(tmp_path):
    return Course(tmp_path / "progress.db")


def _pass_lessons(course, upto):
    for lesson in lessons()[:upto]:
        for i, ex in enumerate(lesson["exercises"]):
            course.finish_round(lesson["id"], i, [{"key": "k", "step": "first", "correct": True}])


def _answers(test, correct=True, wrong_keys=()):
    return [{"key": item["key"], "step": "first", "correct": correct and item["key"] not in wrong_keys}
            for ex in test["exercises"] for item in ex["items"]]


def test_every_item_knows_where_it_was_written():
    for lesson in lessons():
        for ex in lesson["exercises"]:
            for item in ex["items"]:
                if ex["type"] == "dialogue" and item.get("speaker") == "partner":
                    continue
                origin = item_at(item["src"])
                assert origin.get("answer") == item.get("answer") and origin.get("audio") == item.get("audio")
                if ex.get("review"):
                    assert item["src"][0] < lesson["id"]


def test_tests_sample_each_lesson_of_the_unit():
    assert units()[:2] == [1, 2]
    test = build_test(1, 0)
    sources = {item["src"][0] for ex in test["exercises"] for item in ex["items"]}
    assert sources == {l["id"] for l in unit_lessons(1)}
    assert build_test(1, 0) == test  # the same attempt always gets the same sample
    missed = {item_key("say", lessons()[0]["exercises"][0]["items"][2])}
    again = build_test(1, 1, missed)
    assert missed <= {item_key("say", i) for i in again["exercises"][0]["items"]}


def test_finishing_a_unit_needs_its_mastery_test(course):
    _pass_lessons(course, UNIT_SIZE)
    overview = course.overview()
    assert overview["tests"][0]["status"] == "available"
    assert overview["next"] == {"kind": "test", "id": 1}
    assert next(l for l in overview["lessons"] if l["id"] == UNIT_SIZE + 1)["status"] == "locked"
    test = course.test(1)
    out = course.finish_test(1, _answers(test))
    assert out["passed"] and out["kind"] == "mastery"
    assert course.lesson(UNIT_SIZE + 1)["status"] == "available"
    # retaking a passed test for practice can't lose the pass, and a bad retake owes no fix-up lesson
    out = course.finish_test(1, _answers(course.test(1), correct=False))
    assert not out["passed"] and not out["remedial"]
    assert course.overview()["tests"][0]["status"] == "passed"


def test_a_failed_mastery_test_gives_a_fix_up_lesson_then_a_retest(course):
    _pass_lessons(course, UNIT_SIZE)
    test = course.test(1)
    wrong = {test["exercises"][0]["items"][0]["key"], test["exercises"][0]["items"][1]["key"],
             test["exercises"][1]["items"][0]["key"]}
    out = course.finish_test(1, _answers(test, wrong_keys=wrong))
    assert not out["passed"] and out["remedial"] and out["missed"] == 3
    assert course.overview()["next"] == {"kind": "remedial", "id": 1}
    with pytest.raises(NotAvailable):
        course.test(1)
    fix = course.remedial(1)
    assert {i["key"] for ex in fix["exercises"] for i in ex["items"]} == wrong
    for i, ex in enumerate(fix["exercises"]):
        r = course.finish_remedial_round(1, i, [{"key": "k", "step": "first", "correct": True}])
    assert r["lesson_passed"] and r["next"] == {"kind": "test", "id": 1}
    retest = course.test(1)
    assert retest["attempt"] == 2
    assert wrong <= {i["key"] for ex in retest["exercises"] for i in ex["items"]}


def test_placement_tests_out_of_a_unit(course):
    assert course.overview()["tests"][0]["status"] == "skip"
    assert course.overview()["tests"][1]["status"] == "locked"
    out = course.finish_test(1, _answers(course.test(1)))
    assert out["passed"] and out["kind"] == "placement" and out["next_test"] == 2
    overview = course.overview()
    assert all(l["status"] == "passed" and l["placed"] for l in overview["lessons"][:UNIT_SIZE])
    assert overview["current"] == UNIT_SIZE + 1
    # failing a placement test just means starting that unit's lessons: no fix-up lesson
    out = course.finish_test(2, _answers(course.test(2), correct=False))
    assert not out["passed"] and not out["remedial"]
    assert course.overview()["tests"][1]["status"] == "skip"
    assert course.overview()["next"] == {"kind": "lesson", "id": UNIT_SIZE + 1}


def test_review_brings_back_items_missed_recently(course):
    _pass_lessons(course, 3)
    missed = lessons()[0]["exercises"][0]["items"][2]  # собака, from lesson 1
    key = item_key("say", missed)
    course.finish_round(2, 1, [{"key": key, "step": "first", "correct": False}])
    review = course.lesson(4)["exercises"][0]
    assert review["review"] and review["items"][0]["key"] == key
    assert len(review["items"]) == review["review"]
    # once it's right again for the last few tries it drops out of the "missed" pile
    course.finish_round(2, 1, [{"key": key, "step": "first", "correct": True}] * 4)
    assert key not in course.missed_recently()


def test_locked_items_can_only_be_checked_in_their_unit_test(tmp_path, monkeypatch):
    from app import routes_course
    from app.main import app

    monkeypatch.setattr(routes_course, "course", Course(tmp_path / "progress.db"))
    monkeypatch.setattr(routes_course, "decode_to_pcm16k", lambda data: np.full(16000, 0.1, dtype=np.float32))
    monkeypatch.setattr(routes_course, "check_answer", lambda *a: {
        "correct": True, "silent": False, "heard": None, "score": 90, "words": []})
    client = TestClient(app)
    item = next(i for ex in client.get("/api/course/tests/1").json()["exercises"] for i in ex["items"]
                if i["src"][0] > 1)
    lesson, exercise, index = item["src"]
    form = {"exercise": str(exercise), "item": str(index)}
    audio = {"audio": ("a.webm", b"audio", "audio/webm")}
    assert client.post(f"/api/course/{lesson}/check", data=form, files=audio).status_code == 403
    r = client.post(f"/api/course/{lesson}/check", data={**form, "test": "1"}, files=audio)
    assert r.status_code == 200 and r.json()["correct"]
    assert client.post(f"/api/course/{lesson}/check", data={**form, "test": "2"}, files=audio).status_code == 403
    assert client.get("/api/course/tests/2").status_code == 403
    assert client.get("/api/course/tests/99").status_code == 404
    with pytest.raises(LessonLocked):
        Course(tmp_path / "progress.db").lesson(lesson)


def _starter(store, word):
    starter = next(d for d in store.list_decks() if d["name"] == "Starter words")
    return next(c for c in store.list_cards(starter["id"]) if c["plain"] == word)


def test_lesson_words_are_linked_to_flashcards_and_review(tmp_path):
    from app.course import lesson_for
    from app.flashcards import FlashcardStore

    path = tmp_path / "progress.db"
    store = FlashcardStore(path)
    store.sync_builtin_decks([])
    course = Course(path)
    assert lesson_for("к+ошка") == 1 and lesson_for("кошку") == 1 and lesson_for("в+ижу") == 19
    assert lesson_for("+это дом") is None  # only single words are linked
    assert _starter(store, "кошка")["lesson"] == 1
    assert _starter(store, "кошка")["state"] == "new"

    _pass_lessons(course, 1)  # passing a lesson starts its words' flashcard schedule
    cat = _starter(store, "кошка")
    assert cat["state"] != "new" and _starter(store, "машина")["state"] == "new"

    with connect(path) as conn:  # make the card due now
        conn.execute("UPDATE cards SET due = ? WHERE id = ?", (0, cat["id"]))
    _pass_lessons(course, 3)
    review = course.lesson(4)["exercises"][0]["items"]
    practised = next(i for i in review if i.get("card") == cat["id"])
    assert practised["answer"]["plain"] == "кошка" and practised["src"][0] == 1
    reps = store.get_card(cat["id"])["reps"]
    course.finish_round(4, 0, [{"key": practised["key"], "step": "first", "correct": True, "card": cat["id"]}])
    assert store.get_card(cat["id"])["reps"] == reps + 1 and not store.get_card(cat["id"])["is_due"]


def test_dashboard_stats_group_results_by_track(course):
    _pass_lessons(course, 1)
    vocab = lessons()[0]["exercises"][0]["items"][1]
    course.finish_round(1, 0, [{"key": item_key("say", vocab), "step": "first", "correct": False}])
    stats = course.stats()
    tracks = {t["track"]: t for t in stats["tracks"]}
    assert tracks["vocab"]["tries"] == 1 and tracks["vocab"]["accuracy"] == 0
    assert stats["work_on"][0]["key"] == item_key("say", vocab) and stats["work_on"][0]["display"] == "ко́шка"
