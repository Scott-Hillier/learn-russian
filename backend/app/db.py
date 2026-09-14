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
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


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
                _initialised.add(path)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
