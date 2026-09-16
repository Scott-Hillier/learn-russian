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


def test_study_order_daily_limit_and_rating(store):
    store.update_settings(new_per_day=2)
    phrases = deck(store, "Phrases")
    first = store.next_card(phrases["id"])
    assert first["kind"] == "new" and first["card"]["text"] == "Прив+ет"
    assert set(first["intervals"]) == {"again", "hard", "good", "easy"}

    result = store.rate(first["card"]["id"], 3, score=90)
    assert result["card"]["state"] == "learning" and result["card"]["reps"] == 1

    second = store.next_card(phrases["id"])
    assert second["kind"] == "new" and second["card"]["text"] == "Спас+ибо"
    store.rate(second["card"]["id"], 4)

    # Daily limit (2) reached: only the learning card due within the learn-ahead window remains.
    nxt = store.next_card()
    assert nxt["kind"] == "review" and nxt["card"]["text"] == "Прив+ет"
    assert store.remaining()["new"] == 0
    stats = store.stats()
    assert stats["reviewed_today"] == 2 and stats["streak_days"] == 1 and stats["average_score_today"] == 90


def test_practice_ignores_limits_and_schedule(store):
    store.update_settings(new_per_day=0)
    phrases = deck(store, "Phrases")
    assert store.next_card(phrases["id"]) is None  # no new cards allowed today

    queue = store.practice_queue(phrases["id"])
    assert {c["text"] for c in queue} == {"Прив+ет", "Спас+ибо"}

    card = queue[0]
    result = store.rate(card["id"], 3, score=90, practice=True)
    assert result["next_due_in"] is None
    assert result["card"]["state"] == "new" and result["card"]["reps"] == 0  # schedule untouched
    assert store.remaining(phrases["id"])["new"] == 0  # and no new-card allowance spent

    # The attempt still counts towards today's practice.
    assert store.stats()["reviewed_today"] == 1
    store.update_settings(new_per_day=1)
    assert store.next_card(phrases["id"])["kind"] == "new"


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
