"""Local practice history (SQLite): every scored attempt and each letter's score within it."""
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

RECENT = 8           # letter mastery looks at this many most recent occurrences
MASTERED_AVG = 0.8
MASTERED_MIN = 3

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    score INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS letter_scores (
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    letter TEXT NOT NULL,
    score REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS letter_scores_letter ON letter_scores(letter);
"""


@contextmanager
def _connect(path: Path | None = None):
    with _lock:
        conn = sqlite3.connect(path or config.PROGRESS_DB)
        try:
            conn.executescript(SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()


def record_attempt(source: str, target: str, feedback: dict, path: Path | None = None) -> None:
    """Store an attempt's overall score and per-letter scores."""
    with _connect(path) as conn:
        cur = conn.execute("INSERT INTO attempts (created_at, source, target, score) VALUES (?, ?, ?, ?)",
                           (time.time(), source, target, feedback["score"]))
        rows = [(cur.lastrowid, l["char"].lower(), l["score"])
                for w in feedback["words"] for l in w["letters"] if l.get("score") is not None]
        conn.executemany("INSERT INTO letter_scores (attempt_id, letter, score) VALUES (?, ?, ?)", rows)


def letter_mastery(path: Path | None = None) -> dict[str, dict]:
    """Per letter: number of scored occurrences, recent average (0–1) and a status."""
    with _connect(path) as conn:
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
