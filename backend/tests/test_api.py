"""API smoke tests. Speech models are never loaded: TestClient is used without the startup event,
and the attempt test sends silence, which returns before recognition runs."""
import io
import wave

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _silent_wav(seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def test_content_endpoints():
    assert len(client.get("/api/phrases").json()) >= 30
    assert len(client.get("/api/alphabet").json()["letters"]) == 33
    sentences = client.get("/api/sentences").json()
    assert sentences[0]["words"][0]["gloss"] and sentences[0]["chunks"]
    groups = client.get("/api/minimal-pairs").json()
    assert groups and all("recommended" in g for g in groups)
    assert {d["name"] for d in client.get("/api/decks").json()} >= {"Starter words", "Phrases"}


def test_attempt_route_accepts_form_fields():
    r = client.post("/api/attempt", data={"target": "Где метр+о?", "source": "sentence", "timing": "true"},
                    files={"audio": ("a.wav", _silent_wav(), "audio/wav")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score"] == 0 and body["words"][0]["status"] == "missing"


def test_attempt_rejects_non_russian_target():
    r = client.post("/api/attempt", data={"target": "hello"}, files={"audio": ("a.wav", _silent_wav(), "audio/wav")})
    assert r.status_code == 400


def test_flashcard_routes():
    deck = client.post("/api/decks", json={"name": "API test"}).json()
    card = client.post(f"/api/decks/{deck['id']}/cards", json={"russian": "кот", "english": "cat"}).json()
    assert card["display"] == "кот"
    assert client.post(f"/api/decks/{deck['id']}/cards", json={"russian": "cat", "english": "x"}).status_code == 400
    assert client.post(f"/api/study/{card['id']}/rate", json={"rating": 9}).status_code == 400
    practice = client.get(f"/api/study/practice?deck_id={deck['id']}").json()["cards"]
    assert [c["id"] for c in practice] == [card["id"]]
    assert client.post(f"/api/study/{card['id']}/rate", json={"rating": 3, "practice": True}).json()["next_due_in"] is None
    assert client.get("/api/study/practice?deck_id=999999").status_code == 404
    assert client.get("/api/decks/999999/cards").status_code == 404
    assert client.delete(f"/api/decks/{deck['id']}").json() == {"ok": True}
