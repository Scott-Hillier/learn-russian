"""Flashcard decks with FSRS spaced-repetition scheduling."""
import csv
import io
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fsrs import Card, Rating, Scheduler, State

from . import config
from .db import connect
from .text import display_stress, strip_stress, transliterate

DAY_START_HOUR = 4                 # a study "day" rolls over at 4am local time, like Anki
LEARN_AHEAD = timedelta(minutes=20)  # when nothing else is due, show learning cards due soon
DEFAULT_SETTINGS = {"group_size": 10}
MAX_GROUP_SIZE = 100
VOWELS = set("аеёиоуыэюя")

_scheduler = Scheduler()                        # real reviews (fuzzed intervals)
_preview_scheduler = Scheduler(enable_fuzzing=False)  # interval labels on rating buttons


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def needs_stress_mark(russian: str) -> bool:
    """True if some multi-vowel word has neither a '+' mark nor ё (stress unknown)."""
    for word in russian.split():
        vowels = sum(c in VOWELS for c in word.lower())
        if vowels > 1 and "+" not in word and "ё" not in word.lower():
            return True
    return False


def _plain_key(russian: str) -> str:
    # ё is kept distinct from е: всё ("everything") and все ("everyone") are different words.
    return strip_stress(russian).lower().strip()


def _day_start(now: datetime | None = None) -> float:
    now = (now or datetime.now()).astimezone()
    start = now.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return start.timestamp()


def format_interval(delta: timedelta) -> str:
    s = delta.total_seconds()
    if s < 60:
        return "<1m"
    if s < 3600:
        return f"{round(s / 60)}m"
    if s < 86400:
        return f"{round(s / 3600)}h"
    days = s / 86400
    if days < 30:
        return f"{round(days)}d"
    if days < 365:
        return f"{round(days / 30)}mo"
    return f"{days / 365:.1f}y".replace(".0y", "y")


def _validate_card_fields(russian: str, english: str) -> tuple[str, str]:
    russian, english = russian.strip(), english.strip()
    if not russian or not english:
        raise Invalid("Both Russian and English are required.")
    if not any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in russian):
        raise Invalid("The Russian side must contain Cyrillic letters.")
    if len(russian) > 200 or len(english) > 200:
        raise Invalid("Cards are limited to 200 characters per side.")
    return russian, english


class FlashcardStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    # ---------- built-in decks ----------

    def sync_builtin_decks(self, phrases: list[dict]) -> None:
        """Create built-in decks and add any built-in cards that are missing. User edits are kept."""
        starter = json.loads((config.DATA_DIR / "decks" / "starter_words.json").read_text(encoding="utf-8"))
        decks = [
            (starter["slug"], starter["name"], starter["description"],
             [(ru, en, "", unit["title"]) for unit in starter["units"] for ru, en in unit["cards"]]),
            ("phrases", "Phrases", "The survival phrases from the Phrases screen.",
             [(p["text"], p["english"], p.get("note", ""), p["category"]) for p in phrases]),
        ]
        now = time.time()
        with connect(self.path) as conn:
            for slug, name, description, cards in decks:
                row = conn.execute("SELECT id FROM decks WHERE slug = ?", (slug,)).fetchone()
                if row:
                    deck_id = row["id"]
                    conn.execute("UPDATE decks SET name = ?, description = ? WHERE id = ?", (name, description, deck_id))
                else:
                    deck_id = conn.execute(
                        "INSERT INTO decks (slug, name, description, builtin, created_at) VALUES (?, ?, ?, 1, ?)",
                        (slug, name, description, now)).lastrowid
                existing = {r["source_key"] for r in conn.execute(
                    "SELECT source_key FROM cards WHERE deck_id = ?", (deck_id,))}
                for position, (ru, en, notes, tag) in enumerate(cards):
                    key = _plain_key(ru)
                    if key in existing:
                        continue
                    conn.execute(
                        "INSERT INTO cards (deck_id, russian, english, notes, tag, position, source_key, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (deck_id, ru, en, notes, tag, position, key, now))
                    existing.add(key)

    # ---------- settings ----------

    def settings(self) -> dict:
        with connect(self.path) as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        stored = {r["key"]: json.loads(r["value"]) for r in rows}
        out = dict(DEFAULT_SETTINGS)
        # Words used to be introduced per day; carry an old "new_per_day" over as the group size.
        if "group_size" not in stored and stored.get("new_per_day", 0) > 0:
            stored["group_size"] = stored["new_per_day"]
        out.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
        return out

    def update_settings(self, group_size: int) -> dict:
        if not 1 <= group_size <= MAX_GROUP_SIZE:
            raise Invalid(f"Words per group must be between 1 and {MAX_GROUP_SIZE}.")
        with connect(self.path) as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES ('group_size', ?)"
                         " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps(group_size),))
        return self.settings()

    # ---------- decks ----------

    def list_decks(self) -> list[dict]:
        now = time.time()
        with connect(self.path) as conn:
            rows = conn.execute(
                """SELECT d.*,
                     COUNT(c.id) AS total,
                     SUM(c.suspended) AS suspended,
                     SUM(c.reps = 0 AND c.suspended = 0) AS new,
                     SUM(c.reps > 0 AND c.suspended = 0 AND c.due <= ?) AS due,
                     SUM(c.reps > 0 AND c.suspended = 0 AND json_extract(c.fsrs, '$.state') = 2) AS review,
                     SUM(c.reps > 0 AND c.suspended = 0 AND json_extract(c.fsrs, '$.state') IN (1, 3)) AS learning
                   FROM decks d LEFT JOIN cards c ON c.deck_id = d.id
                   GROUP BY d.id ORDER BY d.builtin DESC, d.id""", (now,)).fetchall()
            return [{"id": r["id"], "name": r["name"], "description": r["description"], "builtin": bool(r["builtin"]),
                     "counts": {k: r[k] or 0 for k in ("total", "new", "learning", "review", "due", "suspended")},
                     "group": self._group(conn, r["id"])}
                    for r in rows]

    def create_deck(self, name: str, description: str = "") -> dict:
        name = name.strip()
        if not name:
            raise Invalid("Deck name is required.")
        with connect(self.path) as conn:
            deck_id = conn.execute("INSERT INTO decks (name, description, created_at) VALUES (?, ?, ?)",
                                   (name[:80], description.strip()[:300], time.time())).lastrowid
        return next(d for d in self.list_decks() if d["id"] == deck_id)

    def delete_deck(self, deck_id: int) -> None:
        with connect(self.path) as conn:
            row = conn.execute("SELECT builtin FROM decks WHERE id = ?", (deck_id,)).fetchone()
            if not row:
                raise NotFound("Deck not found.")
            if row["builtin"]:
                raise Invalid("Built-in decks can't be deleted.")
            conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))

    # ---------- cards ----------

    def _card_dict(self, r, now: float | None = None) -> dict:
        now = now or time.time()
        state = "new" if r["reps"] == 0 else {1: "learning", 2: "review", 3: "learning"}[json.loads(r["fsrs"])["state"]]
        return {
            "id": r["id"], "deck_id": r["deck_id"], "text": r["russian"], "display": display_stress(r["russian"]),
            "plain": strip_stress(r["russian"]), "translit": transliterate(r["russian"]), "english": r["english"],
            "notes": r["notes"], "tag": r["tag"], "suspended": bool(r["suspended"]), "state": state,
            "due": r["due"], "is_due": r["reps"] > 0 and r["due"] <= now, "reps": r["reps"], "lapses": r["lapses"],
            "needs_stress": needs_stress_mark(r["russian"]), "builtin": r["source_key"] is not None,
        }

    def list_cards(self, deck_id: int) -> list[dict]:
        with connect(self.path) as conn:
            if not conn.execute("SELECT 1 FROM decks WHERE id = ?", (deck_id,)).fetchone():
                raise NotFound("Deck not found.")
            rows = conn.execute("SELECT * FROM cards WHERE deck_id = ? ORDER BY position, id", (deck_id,)).fetchall()
        now = time.time()
        return [self._card_dict(r, now) for r in rows]

    def get_card(self, card_id: int) -> dict:
        with connect(self.path) as conn:
            r = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not r:
            raise NotFound("Card not found.")
        return self._card_dict(r)

    def add_card(self, deck_id: int, russian: str, english: str, notes: str = "") -> dict:
        russian, english = _validate_card_fields(russian, english)
        with connect(self.path) as conn:
            if not conn.execute("SELECT 1 FROM decks WHERE id = ?", (deck_id,)).fetchone():
                raise NotFound("Deck not found.")
            if self._duplicate(conn, deck_id, russian):
                raise Invalid(f"“{strip_stress(russian)}” is already in this deck.")
            position = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM cards WHERE deck_id = ?",
                                    (deck_id,)).fetchone()[0]
            card_id = conn.execute(
                "INSERT INTO cards (deck_id, russian, english, notes, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (deck_id, russian, english, notes.strip()[:500], position, time.time())).lastrowid
        return self.get_card(card_id)

    @staticmethod
    def _duplicate(conn, deck_id: int, russian: str, exclude_id: int | None = None) -> bool:
        key = _plain_key(russian)
        rows = conn.execute("SELECT id, russian FROM cards WHERE deck_id = ?", (deck_id,)).fetchall()
        return any(_plain_key(r["russian"]) == key and r["id"] != exclude_id for r in rows)

    def update_card(self, card_id: int, russian: str, english: str, notes: str, suspended: bool) -> dict:
        russian, english = _validate_card_fields(russian, english)
        with connect(self.path) as conn:
            row = conn.execute("SELECT deck_id FROM cards WHERE id = ?", (card_id,)).fetchone()
            if not row:
                raise NotFound("Card not found.")
            if self._duplicate(conn, row["deck_id"], russian, exclude_id=card_id):
                raise Invalid(f"“{strip_stress(russian)}” is already in this deck.")
            conn.execute("UPDATE cards SET russian = ?, english = ?, notes = ?, suspended = ? WHERE id = ?",
                         (russian, english, notes.strip()[:500], int(suspended), card_id))
        return self.get_card(card_id)

    def delete_card(self, card_id: int) -> None:
        with connect(self.path) as conn:
            row = conn.execute("SELECT source_key FROM cards WHERE id = ?", (card_id,)).fetchone()
            if not row:
                raise NotFound("Card not found.")
            if row["source_key"] is not None:
                raise Invalid("Built-in cards can't be deleted, but you can suspend them.")
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    def import_csv(self, deck_id: int, data: bytes) -> dict:
        """Import rows of `russian, english[, notes]`. A header row is detected and skipped."""
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise Invalid("The file must be UTF-8 encoded text.")
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        added, skipped, errors = 0, 0, []
        for line_no, row in enumerate(csv.reader(io.StringIO(text), dialect), start=1):
            if not row or not any(cell.strip() for cell in row):
                continue
            if line_no == 1 and row[0].strip().lower() in ("russian", "русский", "front", "word"):
                continue
            if len(row) < 2:
                errors.append(f"Line {line_no}: expected at least two columns (Russian, English).")
                continue
            try:
                self.add_card(deck_id, row[0], row[1], row[2] if len(row) > 2 else "")
                added += 1
            except Invalid as e:
                if "already in this deck" in str(e):
                    skipped += 1
                else:
                    errors.append(f"Line {line_no}: {e}")
        return {"added": added, "skipped_duplicates": skipped, "errors": errors[:20]}

    # ---------- studying ----------

    def next_card(self, deck_id: int | None = None, new_limit: int | None = None) -> dict | None:
        """The next card to study: due learning cards, due reviews, new cards, then learning cards due
        within the next few minutes. New cards come in groups: `new_limit` is how many more this session
        may introduce (by default, the rest of the current group)."""
        now = time.time()
        deck_clause, args = ("AND deck_id = ?", [deck_id]) if deck_id else ("", [])
        with connect(self.path) as conn:
            def pick(where: str, order: str, *params):
                return conn.execute(f"SELECT * FROM cards WHERE suspended = 0 {deck_clause} AND {where} "
                                    f"ORDER BY {order} LIMIT 1", (*args, *params)).fetchone()

            row = (pick("reps > 0 AND due <= ? AND json_extract(fsrs, '$.state') IN (1, 3)", "due", now)
                   or pick("reps > 0 AND due <= ?", "due", now))
            kind = "review"
            if new_limit is None:
                new_limit = self._group(conn, deck_id)["left"]
            if not row and new_limit > 0:
                row = pick("reps = 0", "deck_id, position, id")
                kind = "new"
            if not row:
                row = pick("reps > 0 AND due <= ?", "due", now + LEARN_AHEAD.total_seconds())
                kind = "review"
            if not row:
                return None
            card = self._card_dict(row, now)
        return {"card": card, "kind": kind, "intervals": self.preview_intervals(row),
                "remaining": self.remaining(deck_id)}

    def learned_cards(self) -> list[dict]:
        """The Learned words deck: every card you've started learning, most recently learned first.
        It can be reviewed at any time; those reviews don't reschedule anything."""
        with connect(self.path) as conn:
            rows = conn.execute(
                """SELECT c.*, (SELECT MIN(reviewed_at) FROM reviews r WHERE r.card_id = c.id) AS learned_at
                   FROM cards c WHERE c.reps > 0 AND c.suspended = 0
                   ORDER BY learned_at DESC, c.id DESC""").fetchall()
        now = time.time()
        return [self._card_dict(r, now) for r in rows]

    def _group(self, conn, deck_id: int | None = None) -> dict:
        """Where you are in the groups of new words. Group n is complete once n × size words have been
        learned, and the next group is available straight away."""
        size = self.settings()["group_size"]
        deck_clause, args = ("AND deck_id = ?", [deck_id]) if deck_id else ("", [])
        learned = conn.execute(f"SELECT COUNT(*) FROM cards WHERE reps > 0 {deck_clause}", args).fetchone()[0]
        return {"number": learned // size + 1, "size": size, "left": size - learned % size, "learned": learned}

    def remaining(self, deck_id: int | None = None) -> dict:
        now = time.time()
        deck_clause, args = ("AND deck_id = ?", [deck_id]) if deck_id else ("", [])
        with connect(self.path) as conn:
            due = conn.execute(f"SELECT COUNT(*) FROM cards WHERE suspended = 0 {deck_clause} AND reps > 0 AND due <= ?",
                               (*args, now)).fetchone()[0]
            new_cards = conn.execute(f"SELECT COUNT(*) FROM cards WHERE suspended = 0 {deck_clause} AND reps = 0",
                                     args).fetchone()[0]
            group = self._group(conn, deck_id)
            learned = conn.execute("SELECT COUNT(*) FROM cards WHERE reps > 0 AND suspended = 0").fetchone()[0]
        return {"due": due, "new": min(new_cards, group["left"]), "new_total": new_cards, "group": group,
                "learned_words": learned}

    @staticmethod
    def _fsrs_card(row) -> Card:
        return Card.from_dict(json.loads(row["fsrs"])) if row["fsrs"] else Card(card_id=row["id"])

    def preview_intervals(self, row) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        card = self._fsrs_card(row)
        return {r.name.lower(): format_interval(_preview_scheduler.review_card(card, r, now)[0].due - now)
                for r in Rating}

    def rate(self, card_id: int, rating: int, score: int | None = None, practice: bool = False) -> dict:
        """Record a review. A practice rating (reviewing the Learned words deck) counts towards your stats
        but leaves the card's schedule untouched, so extra passes cost nothing."""
        try:
            rating_enum = Rating(rating)
        except ValueError:
            raise Invalid("Rating must be 1 (Again), 2 (Hard), 3 (Good) or 4 (Easy).")
        now = datetime.now(timezone.utc)
        next_due_in = None
        with connect(self.path) as conn:
            row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
            if not row:
                raise NotFound("Card not found.")
            if not practice:
                before = self._fsrs_card(row)
                after, _ = _scheduler.review_card(before, rating_enum, now)
                lapsed = row["reps"] > 0 and before.state == State.Review and rating_enum == Rating.Again
                conn.execute("UPDATE cards SET fsrs = ?, due = ?, reps = reps + 1, lapses = lapses + ? WHERE id = ?",
                             (json.dumps(after.to_dict()), after.due.timestamp(), int(lapsed), card_id))
                next_due_in = format_interval(after.due - now)
            conn.execute("INSERT INTO reviews (card_id, rating, score, was_new, reviewed_at) VALUES (?, ?, ?, ?, ?)",
                         (card_id, rating, score, int(row["reps"] == 0 and not practice), now.timestamp()))
        card = self.get_card(card_id)
        return {"card": card, "next_due_in": next_due_in}

    def stats(self) -> dict:
        day = _day_start()
        with connect(self.path) as conn:
            today = conn.execute("SELECT COUNT(*), AVG(score) FROM reviews WHERE reviewed_at >= ?", (day,)).fetchone()
            times = [r[0] for r in conn.execute("SELECT DISTINCT reviewed_at FROM reviews ORDER BY reviewed_at DESC")]
        days = sorted({int((day - t) // 86400) + 1 if t < day else 0 for t in times})
        streak = 0
        if days and days[0] <= 1:  # studied today or yesterday
            expected = days[0]
            for d in days:
                if d != expected:
                    break
                streak += 1
                expected += 1
        return {"reviewed_today": today[0], "average_score_today": round(today[1]) if today[1] is not None else None,
                "streak_days": streak, **self.remaining()}


store = FlashcardStore()
