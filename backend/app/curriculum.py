"""Direct Instruction design rules for the course, checked against the lesson files.

tests/test_curriculum.py fails the build if any rule is broken, so content can't drift away from the
method as lessons are added. Words are compared by lemma (pymorphy3), so кошка and кошку count as
the same word.
"""
import json
import re
from functools import lru_cache

from . import config
from .text import normalize_words

MIN_TRACKS = 3
MAX_NEW_WORDS = 8  # new lemmas per lesson
MAX_TEACH_ITEMS = 5  # new items modelled in one teach exercise
REVIEW_WINDOW = 5  # a new word must come back in at least REVIEW_MIN of the next REVIEW_WINDOW lessons
REVIEW_MIN = 2
POSSESSIVES = {"мой", "твой", "наш", "ваш", "свой"}


@lru_cache(maxsize=1)
def _morph():
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


LEMMA_FIXES = {"больший": "большой"}  # pymorphy3 reads «большая» as the comparative «больший»


def lemma(word: str) -> str:
    parses = _morph().parse(word)
    best = parses[0]
    if best.tag.POS in ("ADJS", "PRTS", "PRTF"):  # «читаем» is the verb, not «читаемый»
        best = next((p for p in parses if p.tag.POS == "VERB"), best)
    form = best.normal_form.replace("ё", "е")
    return LEMMA_FIXES.get(form, form)


def _words(text: str) -> list[str]:
    return [w for w in normalize_words(text) if re.search("[а-я]", w)]


def _texts(item: dict) -> tuple[list[str], list[str]]:
    """(spoken answers, everything else in Russian) for one item."""
    produced = [item["answer"]] if "answer" in item else []
    heard = [item[k] for k in ("ask", "line", "audio", "prompt") if k in item]
    if "prompt" in item:
        heard += item.get("options", [])
    return produced, heard


def _confusables() -> list[dict]:
    path = config.DATA_DIR / "course" / "confusables.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _unreliable_pair(a: str, b: str) -> bool:
    """Two forms of one word that the speech checker can't reliably tell apart (see PLAN.md, Phase 8)."""
    pa, pb = _morph().parse(a)[0], _morph().parse(b)[0]
    if lemma(a) != lemma(b):
        return False
    if lemma(a) in POSSESSIVES or {pa.tag.POS, pb.tag.POS} <= {"ADJF", "ADJS"}:
        return a != b  # новый/новая/новое, мой/моя/моё: the endings are short and unstressed
    if pa.tag.POS == pb.tag.POS == "VERB" and pa.normal_form.endswith(("ать", "ять")):
        # читаю/читаем/читают/читает differ only in a quiet ending; past-tense gender (читал/читала) is reliable
        return pa.tag.tense == pb.tag.tense == "pres"
    return False


def introductions(lessons: tuple[dict, ...]) -> dict[str, int]:
    """Lemma → the lesson it first appears in (said, heard or read)."""
    out: dict[str, int] = {}
    for lesson in lessons:
        for ex in lesson["exercises"]:
            for item in ex["items"]:
                produced, heard = _texts(item)
                for text in produced + heard:
                    for w in _words(text):
                        out.setdefault(lemma(w), lesson["id"])
    return out


def word_lemmas(text: str) -> list[str]:
    return [lemma(w) for w in _words(text)]


def check(lessons: tuple[dict, ...]) -> list[str]:
    """Every rule broken by the course (empty when the course follows the design)."""
    problems: list[str] = []
    morph = _morph()
    introduced: dict[str, int] = {}  # lemma -> lesson it first appears in
    taught: set[str] = set()  # lemmas modelled in a teach exercise so far
    used_in: dict[str, set[int]] = {}

    for lesson in lessons:
        at = f"lesson {lesson['id']}"
        tracks = {ex["track"] for ex in lesson["exercises"]}
        if len(tracks) < MIN_TRACKS:
            problems.append(f"{at}: only {len(tracks)} tracks (needs {MIN_TRACKS})")
        if lesson["id"] > 1 and "review" not in tracks:
            problems.append(f"{at}: no review exercise")

        new_here: list[str] = []
        for e_idx, ex in enumerate(lesson["exercises"]):
            where = f"{at} exercise {e_idx + 1} ({ex['title']})"
            if ex["type"] == "teach" and len(ex["items"]) > MAX_TEACH_ITEMS:
                problems.append(f"{where}: teaches {len(ex['items'])} items at once (max {MAX_TEACH_ITEMS})")
            for item in ex["items"]:
                produced, heard = _texts(item)
                for text in produced + heard:
                    for w in _words(text):
                        if not morph.word_is_known(w):
                            problems.append(f"{where}: '{w}' isn't a known Russian word (typo?)")
                        lem = lemma(w)
                        used_in.setdefault(lem, set()).add(lesson["id"])
                        if lem not in introduced:
                            introduced[lem] = lesson["id"]
                            new_here.append(lem)
                if ex["type"] == "teach":
                    taught.update(lemma(w) for t in produced for w in _words(t))
                for text in produced:
                    for w in _words(text):
                        if lemma(w) not in taught:
                            problems.append(f"{where}: says '{w}' before it has been taught")
                for distractor in item.get("distractors", []):
                    a, b = _words(item.get("answer", "")), _words(distractor)
                    diff = [(x, y) for x, y in zip(a, b) if x != y]
                    if len(a) == len(b) and len(diff) == 1 and _unreliable_pair(*diff[0]):
                        problems.append(f"{where}: '{item['answer']}' vs '{distractor}' differ only in "
                                        f"{diff[0][0]}/{diff[0][1]}, which the checker can't hear reliably")
        if len(new_here) > MAX_NEW_WORDS:
            problems.append(f"{at}: {len(new_here)} new words (max {MAX_NEW_WORDS}): {', '.join(new_here)}")

    last = lessons[-1]["id"] if lessons else 0
    for lem, first in introduced.items():
        later = [i for i in range(first + 1, min(first + REVIEW_WINDOW, last) + 1)]
        needed = min(REVIEW_MIN, len(later))
        seen = len(used_in[lem] & set(later))
        if seen < needed:
            problems.append(f"lesson {first}: new word '{lem}' comes back in {seen} of the next {len(later)} "
                            f"lessons (needs {needed})")

    for group in _confusables():
        members = [(w, introduced.get(lemma(w))) for w in group["words"]]
        members = [(w, i) for w, i in members if i is not None]
        for x, (w1, i1) in enumerate(members):
            for w2, i2 in members[x + 1:]:
                if abs(i1 - i2) < group["gap"]:
                    problems.append(f"confusable '{w1}' (lesson {i1}) and '{w2}' (lesson {i2}) are introduced "
                                    f"less than {group['gap']} lessons apart")
    return problems
