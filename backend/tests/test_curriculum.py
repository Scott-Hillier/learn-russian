"""The course must follow the Direct Instruction design rules (see app/curriculum.py and PLAN.md)."""
from app.course import lessons
from app.curriculum import check


def test_course_follows_the_design_rules():
    problems = check(lessons())
    assert problems == [], "\n".join(problems)


def test_only_contrasts_the_checker_cant_hear_are_flagged():
    from app.curriculum import _unreliable_pair

    assert _unreliable_pair("знаю", "знаем") and _unreliable_pair("мой", "моя")
    assert _unreliable_pair("большой", "большая")
    assert not _unreliable_pair("знал", "знала")  # past-tense gender is heard reliably
    assert not _unreliable_pair("кошка", "кошку") and not _unreliable_pair("говорю", "говорит")
