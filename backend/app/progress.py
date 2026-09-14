"""Practice history: every scored attempt and each letter's score within it."""
import time
from datetime import datetime, timedelta
from pathlib import Path

from .db import connect

RECENT = 8           # letter mastery looks at this many most recent occurrences
MASTERED_AVG = 0.8
MASTERED_MIN = 3


def record_attempt(source: str, target: str, feedback: dict, path: Path | None = None) -> None:
    """Store an attempt's overall score and per-letter scores."""
    with connect(path) as conn:
        cur = conn.execute("INSERT INTO attempts (created_at, source, target, score) VALUES (?, ?, ?, ?)",
                           (time.time(), source, target, feedback["score"]))
        rows = [(cur.lastrowid, l["char"].lower(), l["score"])
                for w in feedback["words"] for l in w["letters"] if l.get("score") is not None]
        conn.executemany("INSERT INTO letter_scores (attempt_id, letter, score) VALUES (?, ?, ?)", rows)


def _study_day(ts: float) -> str:
    """Local calendar date of a timestamp, with the day rolling over at DAY_START_HOUR (like flashcards)."""
    from .flashcards import DAY_START_HOUR

    return (datetime.fromtimestamp(ts) - timedelta(hours=DAY_START_HOUR)).date().isoformat()


def summary(days: int = 30, path: Path | None = None) -> dict:
    """Everything the progress dashboard needs, computed from the local history."""
    today = datetime.fromisoformat(_study_day(time.time())).date()
    window = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    with connect(path) as conn:
        attempts = conn.execute("SELECT created_at, source, score FROM attempts").fetchall()
        reviews = conn.execute("SELECT reviewed_at, rating FROM reviews").fetchall()
        cards = conn.execute(
            """SELECT
                 SUM(reps > 0 AND json_extract(fsrs, '$.state') = 2) AS learned,
                 SUM(reps > 0 AND json_extract(fsrs, '$.state') IN (1, 3)) AS learning,
                 SUM(reps = 0) AS new
               FROM cards WHERE suspended = 0""").fetchone()

    daily = {d: {"date": d, "attempts": 0, "score_sum": 0, "reviews": 0} for d in window}
    active_days: set[str] = set()
    by_source: dict[str, int] = {}
    for ts, source, score in attempts:
        day = _study_day(ts)
        active_days.add(day)
        by_source[source] = by_source.get(source, 0) + 1
        if day in daily:
            daily[day]["attempts"] += 1
            daily[day]["score_sum"] += score
    for ts, _rating in reviews:
        day = _study_day(ts)
        active_days.add(day)
        if day in daily:
            daily[day]["reviews"] += 1

    streak = 0
    cursor = today if today.isoformat() in active_days else today - timedelta(days=1)
    while cursor.isoformat() in active_days:
        streak += 1
        cursor -= timedelta(days=1)

    mastery = letter_mastery(path)
    problems = sorted((dict(letter=l, **m) for l, m in mastery.items() if m["count"] >= MASTERED_MIN and m["average"] < 0.85),
                      key=lambda m: m["average"])[:5]
    return {
        "totals": {"attempts": len(attempts), "reviews": len(reviews), "active_days": len(active_days),
                   "streak_days": streak,
                   "average_score": round(sum(a[2] for a in attempts) / len(attempts)) if attempts else None},
        "daily": [{"date": d["date"], "attempts": d["attempts"], "reviews": d["reviews"],
                   "average_score": round(d["score_sum"] / d["attempts"]) if d["attempts"] else None}
                  for d in daily.values()],
        "by_source": by_source,
        "letters": mastery,
        "problem_letters": problems,
        "flashcards": {k: cards[k] or 0 for k in ("learned", "learning", "new")},
    }


def best_scores(source: str, path: Path | None = None) -> dict[str, int]:
    """Best overall score per target text for one practice source."""
    with connect(path) as conn:
        rows = conn.execute("SELECT target, MAX(score) FROM attempts WHERE source = ? GROUP BY target",
                            (source,)).fetchall()
    return {target: best for target, best in rows}


def letter_mastery(path: Path | None = None) -> dict[str, dict]:
    """Per letter: number of scored occurrences, recent average (0–1) and a status."""
    with connect(path) as conn:
        rows = conn.execute("SELECT letter, score FROM letter_scores ORDER BY attempt_id DESC").fetchall()
    recent: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for letter, score in rows:
        counts[letter] = counts.get(letter, 0) + 1
        if len(recent.setdefault(letter, [])) < RECENT:
            recent[letter].append(score)
    out = {}
    for letter, scores in recent.items():
        avg = sum(scores) / len(scores)
        status = "mastered" if len(scores) >= MASTERED_MIN and avg >= MASTERED_AVG else "learning"
        out[letter] = {"count": counts[letter], "average": round(avg, 3), "status": status}
    return out
