"""SQLite access for the local user database (practice history, flashcards, settings)."""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import config

_lock = threading.RLock()
_initialised: set[Path] = set()

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

CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE,                     -- set for built-in decks
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    builtin INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    russian TEXT NOT NULL,                -- with '+' stress marks
    english TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    tag TEXT NOT NULL DEFAULT '',         -- e.g. unit title
    position INTEGER NOT NULL,            -- order new cards are introduced
    source_key TEXT,                      -- original text of a built-in card
    suspended INTEGER NOT NULL DEFAULT 0,
    fsrs TEXT,                            -- serialised fsrs.Card, NULL while new
    due REAL,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS cards_deck ON cards(deck_id, position);
CREATE INDEX IF NOT EXISTS cards_due ON cards(due);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    score INTEGER,
    was_new INTEGER NOT NULL,
    reviewed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS reviews_time ON reviews(reviewed_at);
CREATE TABLE IF NOT EXISTS course_progress (
    lesson_id INTEGER PRIMARY KEY,
    exercise INTEGER NOT NULL DEFAULT 0,  -- index of the first exercise not yet passed
    started_at REAL NOT NULL,
    passed_at REAL,                       -- set once every exercise has been passed
    placed INTEGER NOT NULL DEFAULT 0     -- passed by passing its unit's test rather than the lesson itself
);
CREATE TABLE IF NOT EXISTS course_tests (
    id INTEGER PRIMARY KEY,
    unit INTEGER NOT NULL,                -- unit n covers lessons 5n-4 … 5n
    kind TEXT NOT NULL,                   -- mastery (after the unit's lessons) | placement (testing out)
    accuracy REAL NOT NULL,
    passed INTEGER NOT NULL,
    missed TEXT NOT NULL DEFAULT '[]',    -- JSON list of item keys answered wrongly
    remedial_exercise INTEGER NOT NULL DEFAULT 0,
    remedial_passed_at REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS course_results (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL,
    exercise INTEGER NOT NULL,
    item_key TEXT NOT NULL,               -- e.g. "say:это кошка", "hear:кошка"
    step TEXT NOT NULL,                   -- first | practice | retest | delayed | test
    correct INTEGER NOT NULL,
    override INTEGER NOT NULL DEFAULT 0,  -- learner said the checker was wrong
    score INTEGER,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS course_results_item ON course_results(item_key);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# Columns added after a table was first created: (table, column, definition).
MIGRATIONS = [("course_progress", "placed", "INTEGER NOT NULL DEFAULT 0")]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, definition in MIGRATIONS:
        if column not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@contextmanager
def connect(path: Path | None = None):
    """Serialised connection with foreign keys on; commits on success."""
    path = Path(path or config.PROGRESS_DB)
    with _lock:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if path not in _initialised:
                conn.executescript(SCHEMA)
                _migrate(conn)
                _initialised.add(path)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
