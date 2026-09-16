from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .flashcards import Invalid, NotFound, store

router = APIRouter(prefix="/api")

MAX_IMPORT_BYTES = 2 * 1024 * 1024


class DeckIn(BaseModel):
    name: str = Field(max_length=80)
    description: str = Field("", max_length=300)


class CardIn(BaseModel):
    russian: str = Field(max_length=200)
    english: str = Field(max_length=200)
    notes: str = Field("", max_length=500)


class CardUpdate(CardIn):
    suspended: bool = False


class RatingIn(BaseModel):
    rating: int
    score: int | None = Field(None, ge=0, le=100)
    practice: bool = False  # free practice: record the attempt but don't reschedule the card


class SettingsIn(BaseModel):
    new_per_day: int


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFound as e:
        raise HTTPException(404, str(e))
    except Invalid as e:
        raise HTTPException(400, str(e))


@router.get("/decks")
def list_decks():
    return store.list_decks()


@router.post("/decks")
def create_deck(body: DeckIn):
    return _call(store.create_deck, body.name, body.description)


@router.delete("/decks/{deck_id}")
def delete_deck(deck_id: int):
    _call(store.delete_deck, deck_id)
    return {"ok": True}


@router.get("/decks/{deck_id}/cards")
def list_cards(deck_id: int):
    return _call(store.list_cards, deck_id)


@router.post("/decks/{deck_id}/cards")
def add_card(deck_id: int, body: CardIn):
    return _call(store.add_card, deck_id, body.russian, body.english, body.notes)


@router.post("/decks/{deck_id}/import")
async def import_cards(deck_id: int, file: UploadFile = File(...)):
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(400, "CSV files are limited to 2 MB.")
    _call(store.list_cards, deck_id)  # 404 if the deck doesn't exist
    return _call(store.import_csv, deck_id, data)


@router.put("/cards/{card_id}")
def update_card(card_id: int, body: CardUpdate):
    return _call(store.update_card, card_id, body.russian, body.english, body.notes, body.suspended)


@router.delete("/cards/{card_id}")
def delete_card(card_id: int):
    _call(store.delete_card, card_id)
    return {"ok": True}


@router.get("/study/next")
def next_card(deck_id: int | None = None):
    return {"next": store.next_card(deck_id), "remaining": store.remaining(deck_id)}


@router.get("/study/practice")
def practice(deck_id: int | None = None):
    return {"cards": _call(store.practice_queue, deck_id)}


@router.post("/study/{card_id}/rate")
def rate(card_id: int, body: RatingIn):
    return _call(store.rate, card_id, body.rating, body.score, body.practice)


@router.get("/study/stats")
def stats():
    return store.stats()


@router.get("/settings")
def get_settings():
    return store.settings()


@router.put("/settings")
def put_settings(body: SettingsIn):
    return _call(store.update_settings, body.new_per_day)
