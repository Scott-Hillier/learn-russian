"""The course must follow the Direct Instruction design rules (see app/curriculum.py and PLAN.md)."""
from app.course import lessons
from app.curriculum import check


def test_course_follows_the_design_rules():
    problems = check(lessons())
    assert problems == [], "\n".join(problems)
