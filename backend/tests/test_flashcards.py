import json
import re
import time

import pytest

from app import config
from app.flashcards import FlashcardStore, Invalid, format_interval, needs_stress_mark
from app.speech.pronunciation import VOWELS

PHRASES = [{"text": "Прив+ет", "english": "Hi", "category": "Greetings"},
           {"text": "Спас+ибо", "english": "Thank you", "category": "Polite", "note": "n"}]


@pytest.fixture
def store(tmp_path):
    s = FlashcardStore(tmp_path / "test.db")
    s.sync_builtin_decks(PHRASES)
    return s


def deck(store, name):
    return next(d for d in store.list_decks() if d["name"] == name)


def test_starter_deck_content_is_well_formed():
    data = json.loads((config.DATA_DIR / "decks" / "starter_words.json").read_text(encoding="utf-8"))
    cards = [c for unit in data["units"] for c in unit["cards"]]
    assert len(cards) >= 250
    for ru, en in cards:
        assert en.strip()
        assert not re.search(r"\+(?![аеёиоуыэюяАЕЁИОУЫЭЮЯ])", ru), ru
        assert not needs_stress_mark(ru), f"missing stress mark: {ru}"
        assert sum(c in VOWELS for c in ru.lower()) > 0 or ru in ("в", "к", "с"), ru


def test_builtin_sync_is_idempotent_and_keeps_edits(store):
    starter = deck(store, "Starter words")
    data = json.loads((config.DATA_DIR / "decks" / "starter_words.json").read_text(encoding="utf-8"))
    assert starter["builtin"] and starter["counts"]["new"] == starter["counts"]["total"]
    assert starter["counts"]["total"] == sum(len(u["cards"]) for u in data["units"])  # всё and все both kept
    card = store.list_cards(starter["id"])[0]
    store.update_card(card["id"], card["text"], "me, myself", "", False)
    store.sync_builtin_decks(PHRASES)
    assert deck(store, "Starter words")["counts"]["total"] == starter["counts"]["total"]
    assert store.get_card(card["id"])["english"] == "me, myself"
    assert deck(store, "Phrases")["counts"]["total"] == 2


def test_custom_deck_cards_and_duplicates(store):
    d = store.create_deck("My words")
    card = store.add_card(d["id"], "кн+ига", "book")
    assert card["display"] == "кни́га" and card["translit"] == "kníga" and not card["needs_stress"]
    with pytest.raises(Invalid):
        store.add_card(d["id"], "книга", "book again")
    with pytest.raises(Invalid):
        store.add_card(d["id"], "book", "not russian")
    assert store.add_card(d["id"], "м+ама", "mum")["needs_stress"] is False
    assert needs_stress_mark("молоко")
    store.delete_card(card["id"])
    assert len(store.list_cards(d["id"])) == 1


def test_builtin_cards_and_decks_cannot_be_deleted(store):
    starter = deck(store, "Starter words")
    with pytest.raises(Invalid):
        store.delete_deck(starter["id"])
    with pytest.raises(Invalid):
        store.delete_card(store.list_cards(starter["id"])[0]["id"])


def test_csv_import(store):
    d = store.create_deck("Imported")
    data = "russian,english,notes\nкот,cat,\nс+обака;dog\n\nкот,cat again\nhello,world\nодно\n".encode()
    result = store.import_csv(d["id"], data)
    assert result["added"] == 1 and result["skipped_duplicates"] == 1
    assert len(result["errors"]) == 3  # "с+обака;dog" is one column, "hello" not Cyrillic, "одно" one column
    tsv = "дом\thouse\nлес\tforest\n".encode()
    assert store.import_csv(d["id"], tsv)["added"] == 2


def test_study_order_and_groups(store):
    store.update_settings(group_size=1)
    phrases = deck(store, "Phrases")
    first = store.next_card(phrases["id"])
    assert first["kind"] == "new" and first["card"]["text"] == "Прив+ет"
    assert set(first["intervals"]) == {"again", "hard", "good", "easy"}
    assert first["remaining"]["group"] == {"number": 1, "size": 1, "left": 1, "learned": 0}

    result = store.rate(first["card"]["id"], 3, score=90)
    assert result["card"]["state"] == "learning" and result["card"]["reps"] == 1

    # A session that has used up its group only gets the learning card back (learn-ahead)...
    nxt = store.next_card(phrases["id"], new_limit=0)
    assert nxt["kind"] == "review" and nxt["card"]["text"] == "Прив+ет"
    # ...but the next group is available straight away, with no waiting for tomorrow.
    second = store.next_card(phrases["id"])
    assert second["kind"] == "new" and second["card"]["text"] == "Спас+ибо"
    assert second["remaining"]["group"]["number"] == 2
    store.rate(second["card"]["id"], 4)

    remaining = store.remaining(phrases["id"])
    assert remaining["new"] == 0 and remaining["group"]["learned"] == 2 and remaining["learned_words"] == 2
    stats = store.stats()
    assert stats["reviewed_today"] == 2 and stats["streak_days"] == 1 and stats["average_score_today"] == 90


def test_learned_words_deck(store):
    assert store.learned_cards() == []
    phrases = deck(store, "Phrases")
    for _ in range(2):
        store.rate(store.next_card(phrases["id"], new_limit=1)["card"]["id"], 4)
    learned = store.learned_cards()
    assert [c["text"] for c in learned] == ["Спас+ибо", "Прив+ет"]  # most recently learned first

    # Reviewing a learned word records the attempt but leaves its schedule alone.
    card = learned[0]
    result = store.rate(card["id"], 1, score=40, practice=True)
    assert result["next_due_in"] is None
    assert result["card"]["reps"] == card["reps"] and result["card"]["due"] == card["due"]
    assert store.stats()["reviewed_today"] == 3


def test_group_size_setting(store):
    from app.db import connect
    with connect(store.path) as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('new_per_day', '7')")
    assert store.settings() == {"group_size": 7}  # carried over from the old per-day setting
    assert store.update_settings(group_size=12) == {"group_size": 12}
    with pytest.raises(Invalid):
        store.update_settings(group_size=0)


def test_rating_validation(store):
    card = store.next_card()["card"]
    with pytest.raises(Invalid):
        store.rate(card["id"], 7)


def test_format_interval():
    from datetime import timedelta
    assert format_interval(timedelta(seconds=30)) == "<1m"
    assert format_interval(timedelta(minutes=10)) == "10m"
    assert format_interval(timedelta(days=3)) == "3d"
    assert format_interval(timedelta(days=90)) == "3mo"
    assert format_interval(timedelta(days=730)) == "2y"
