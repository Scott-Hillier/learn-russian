import json
import re

from app import config, progress
from app.speech.pronunciation import VOWELS

ALPHABET = json.loads((config.DATA_DIR / "alphabet.json").read_text(encoding="utf-8"))
RUSSIAN_ALPHABET = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"


def _all_texts():
    for letter in ALPHABET["letters"]:
        yield from (ex["text"] for ex in letter["examples"])
        yield from letter["syllables"]
    for lesson in ALPHABET["lessons"]:
        yield from (w["text"] for w in lesson["words"])


def test_all_33_letters_in_order():
    assert "".join(l["upper"] for l in ALPHABET["letters"]) == RUSSIAN_ALPHABET
    for l in ALPHABET["letters"]:
        assert l["lower"] == l["upper"].lower()
        assert l["kind"] in ("vowel", "consonant", "sign")
        assert l["examples"] and l["syllables"] and l["sound"] and l["latin"]


def test_lessons_cover_every_letter_once():
    taught = [c for lesson in ALPHABET["lessons"] for c in lesson["letters"]]
    assert sorted(taught) == sorted(RUSSIAN_ALPHABET) and len(taught) == 33


def test_lesson_words_only_use_letters_already_taught():
    known = set()
    for lesson in ALPHABET["lessons"]:
        known |= {c.lower() for c in lesson["letters"]}
        for w in lesson["words"]:
            unknown = {c for c in w["text"].lower() if c.isalpha()} - known
            assert not unknown, f"lesson {lesson['id']} word {w['text']} uses untaught {unknown}"


def test_stress_marks_precede_vowels_and_multi_vowel_words_are_marked():
    for text in _all_texts():
        for word in text.split():
            assert not re.search(r"\+(?![аеёиоуыэюяАЕЁИОУЫЭЮЯ])", word), f"bad stress mark in {word}"
            vowels = [c for c in word.lower() if c in VOWELS]
            if len(vowels) > 1 and "ё" not in word.lower():
                assert "+" in word, f"missing stress mark in {word}"


def test_progress_mastery(tmp_path):
    db = tmp_path / "p.db"

    def fb(scores):
        return {"score": 90, "words": [{"letters": [{"char": c, "score": s} for c, s in scores]
                                        + [{"char": "в", "score": None}]}]}

    for _ in range(3):
        progress.record_attempt("letter", "мы", fb([("м", 1.0), ("Ы", 0.4)]), path=db)
    m = progress.letter_mastery(path=db)
    assert m["м"] == {"count": 3, "average": 1.0, "status": "mastered"}
    assert m["ы"]["status"] == "learning"
    assert "в" not in m


def test_progress_summary(tmp_path):
    db = tmp_path / "s.db"
    fb = {"score": 80, "words": [{"letters": [{"char": "ы", "score": 0.4}, {"char": "м", "score": 1.0}]}]}
    for _ in range(3):
        progress.record_attempt("phrase", "мы", fb, path=db)
    progress.record_attempt("sentence", "Где метр+о?", {"score": 100, "words": []}, path=db)
    s = progress.summary(days=7, path=db)
    assert s["totals"]["attempts"] == 4 and s["totals"]["streak_days"] == 1 and s["totals"]["average_score"] == 85
    assert len(s["daily"]) == 7 and s["daily"][-1]["attempts"] == 4 and s["daily"][-1]["average_score"] == 85
    assert s["by_source"] == {"phrase": 3, "sentence": 1}
    assert [p["letter"] for p in s["problem_letters"]] == ["ы"]
    assert s["flashcards"] == {"learned": 0, "learning": 0, "new": 0}
