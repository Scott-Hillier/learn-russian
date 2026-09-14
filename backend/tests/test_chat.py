import json

import pytest
from fastapi.testclient import TestClient

from app import chat, config
from app.main import app
from app.flashcards import needs_stress_mark

SCENARIOS = json.loads((config.DATA_DIR / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
CAFE = next(s for s in SCENARIOS if s["id"] == "cafe")


class FakeOllama:
    """Replaces chat._post: returns queued message contents and records requests."""

    def __init__(self, *contents):
        self.contents = list(contents)
        self.requests = []

    def __call__(self, path, payload, timeout=120):
        self.requests.append(payload)
        content = self.contents.pop(0)
        return {"message": {"content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)}}


def test_scenarios_are_well_formed():
    assert len(SCENARIOS) >= 5
    for s in SCENARIOS:
        assert s["role"] and s["setting"] and s["goals"]
        for item in [s["opening"], *s["phrases"]]:
            assert item["english"] and not needs_stress_mark(item["text"].replace("?", "").replace("!", "")), item


def test_reply_cleans_transliteration_and_uses_history(monkeypatch):
    fake = FakeOllama({"reply": "Кофе с молоком. Что ещё?", "translation": "Coffee with milk. Anything else?",
                       "suggestions": [{"russian": "Это дорого? (Eto dorogo?)", "english": "Is it expensive?"},
                                       {"russian": "Nothing", "english": "Nothing"}]})
    monkeypatch.setattr(chat, "_post", fake)
    history = [{"role": "partner", "text": "Здравствуйте! Что вы хотите?"}, {"role": "learner", "text": "Кофе с молоком."}]
    out = chat.reply(CAFE, history)
    assert out["reply"] == "Кофе с молоком. Что ещё?"
    assert out["suggestions"] == [{"russian": "Это дорого?", "english": "Is it expensive?"}]
    roles = [m["role"] for m in fake.requests[0]["messages"]]
    assert roles == ["system", "assistant", "user"]
    assert "waiter" in fake.requests[0]["messages"][0]["content"]


def test_reply_retries_malformed_json_and_non_russian(monkeypatch):
    good = {"reply": "Хорошо!", "translation": "Good!", "suggestions": []}
    fake = FakeOllama("{not json", {"reply": "One hundred rubles", "translation": "", "suggestions": []}, good)
    monkeypatch.setattr(chat, "_post", fake)
    assert chat.reply(CAFE, [{"role": "learner", "text": "Сколько стоит?"}])["reply"] == "Хорошо!"
    assert len(fake.requests) == 3


def test_check_correct_sentence_ignores_punctuation_and_yo(monkeypatch):
    monkeypatch.setattr(chat, "_post", FakeOllama({"analysis": "ok", "corrected": "Ещё чай"}))
    assert chat.check("еще чай.")["status"] == "correct"


def test_check_returns_highlighted_correction(monkeypatch):
    monkeypatch.setattr(chat, "_post", FakeOllama({"analysis": "молоко needs instrumental", "corrected": "Я хочу кофе с молоком."}))
    out = chat.check("Я хочу кофе с молоко.")
    assert out["status"] == "corrected" and out["corrected"] == "Я хочу кофе с молоком."
    assert [d for d in out["diff"] if d["kind"] != "same"] == [{"text": "молоко", "kind": "removed"},
                                                               {"text": "молоком.", "kind": "changed"}]


def test_check_skips_heavy_rewrites_and_non_russian(monkeypatch):
    monkeypatch.setattr(chat, "_post", FakeOllama({"analysis": "", "corrected": "Мне, пожалуйста, большую чашку чёрного чая"}))
    assert chat.check("Я хочу чай")["status"] == "skipped"
    assert chat.check("hello there")["status"] == "skipped"  # no model call for non-Russian


def test_status_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URL", "http://127.0.0.1:9")
    assert chat.status() == {"running": False, "model": config.CHAT_MODEL, "installed": False}


def test_chat_routes(monkeypatch):
    client = TestClient(app)
    scenarios = client.get("/api/chat/scenarios").json()
    assert scenarios[0]["opening"]["display"]
    monkeypatch.setattr(chat, "_post", FakeOllama({"reply": "Привет!", "translation": "Hi!", "suggestions": []}))
    r = client.post("/api/chat/reply", json={"scenario_id": "cafe", "history": [{"role": "learner", "text": "Прив+ет"}]})
    assert r.status_code == 200 and r.json()["reply"] == "Привет!"
    assert client.post("/api/chat/reply", json={"scenario_id": "nope", "history": []}).status_code == 404

    def down(*_a, **_k):
        raise chat.ChatUnavailable("Can't reach Ollama")
    monkeypatch.setattr(chat, "_post", down)
    assert client.post("/api/chat/check", json={"text": "Я хочу чай"}).status_code == 503
