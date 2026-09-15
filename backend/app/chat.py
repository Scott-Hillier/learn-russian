"""Conversation partner: role-play replies and grammar checks from a local LLM served by Ollama.

Model testing (gemma3:4b vs qwen2.5:3b) shaped two design choices:
- The grammar check asks for an analysis and a minimally corrected sentence, and *we* decide whether
  anything changed. Asking the model for a yes/no verdict gave answers that contradicted its own
  explanation.
- The model's grammar explanations were often wrong, so only the corrected sentence is shown
  (with the changed words highlighted), never the model's explanation.
"""
import json
import logging
import re
import urllib.error
import urllib.request
from difflib import SequenceMatcher

from . import config
from .text import expand_numbers

log = logging.getLogger(__name__)

CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
LATIN = re.compile(r"[a-z]", re.IGNORECASE)
MAX_HISTORY = 16  # most recent messages sent to the model

LEVELS = {
    "beginner": "1-2 short sentences, at most 8 words each, only very common words, mostly present tense",
    "elementary": "1-3 sentences, at most 12 words each, common everyday words",
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "maxLength": 300},
        "translation": {"type": "string", "maxLength": 300},
        "suggestions": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {"type": "object",
                      "properties": {"russian": {"type": "string", "maxLength": 120},
                                     "english": {"type": "string", "maxLength": 120}},
                      "required": ["russian", "english"]},
        },
    },
    "required": ["reply", "translation", "suggestions"],
}

CHECK_SCHEMA = {
    "type": "object",
    "properties": {"analysis": {"type": "string", "maxLength": 400},
                   "corrected": {"type": "string", "maxLength": 300}},
    "required": ["analysis", "corrected"],
}

CHECK_SYSTEM = """You are a careful Russian teacher. A beginner wrote one Russian sentence. Check it word by word.
1. "analysis": in English, briefly check each word's form (case ending, gender agreement, verb form). Names and loanwords like кофе are fine.
2. "corrected": the sentence rewritten with the smallest possible changes so it is correct. If nothing is wrong, copy the sentence exactly.
Ignore punctuation, capital letters, and ё written as е. Do not rewrite correct sentences to sound nicer."""


class ChatUnavailable(Exception):
    pass


def _post(path: str, payload: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(f"{config.OLLAMA_URL}{path}", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise ChatUnavailable(f"Ollama error: {e.read().decode(errors='ignore')[:200]}")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ChatUnavailable(f"Can't reach Ollama at {config.OLLAMA_URL} ({e}).")


def status() -> dict:
    """Whether Ollama is running and the chat model is installed."""
    try:
        with urllib.request.urlopen(f"{config.OLLAMA_URL}/api/tags", timeout=3) as resp:
            models = [m["name"] for m in json.load(resp).get("models", [])]
    except Exception:
        return {"running": False, "model": config.CHAT_MODEL, "installed": False}
    installed = any(m == config.CHAT_MODEL or m == f"{config.CHAT_MODEL}:latest" for m in models)
    return {"running": True, "model": config.CHAT_MODEL, "installed": installed}


def _structured_chat(messages: list[dict], schema: dict, temperature: float) -> dict:
    """One structured-output call; retries once if the model returns malformed JSON."""
    last_error = None
    for _ in range(2):
        data = _post("/api/chat", {
            "model": config.CHAT_MODEL, "messages": messages, "stream": False, "format": schema,
            "keep_alive": "10m", "options": {"temperature": temperature, "num_predict": 400},
        })
        try:
            return json.loads(data["message"]["content"])
        except (KeyError, json.JSONDecodeError) as e:
            last_error = e
            log.warning("Chat model returned malformed JSON; retrying")
    raise ChatUnavailable(f"The chat model returned malformed output ({last_error}).")


def _clean_russian(text: str) -> str:
    """Tidy the model's Russian: drop bracketed transliterations and spell any digits out.

    Transliterations look like "Это дорого? (Eto dorogo?)". Digits are spelled out because nothing
    downstream can handle them — the voice skips them and the scorer only sees letters — and because
    a learner needs to see "двести пятьдесят", not "250". The prompt asks for words already, so this
    is the fallback for when the model writes digits anyway.
    """
    text = re.sub(r"\s*\([^)]*[A-Za-z][^)]*\)", "", text)
    return expand_numbers(text)


def system_prompt(scenario: dict, level: str) -> str:
    goals = "; ".join(scenario["goals"])
    return f"""You are role-playing {scenario['role']}, talking with a learner of Russian.
{scenario['setting']}
The learner's goals: {goals}.
Rules:
- Reply in simple, natural, grammatically correct Russian: {LEVELS.get(level, LEVELS['beginner'])}.
- Never use English or Latin letters in "reply".
- Write every number as Russian words, correctly declined: "двести пятьдесят рублей", never "250 рублей".
- Respond directly to what the learner just said and move the conversation forward, usually ending with a simple question.
- If the learner writes in English or seems lost, reply with an even simpler Russian sentence.
- "translation": the English translation of your reply.
- "suggestions": exactly 2 short, correct Russian sentences the learner could say next (fitting your reply), each with English."""


def reply(scenario: dict, history: list[dict], level: str = "beginner") -> dict:
    """Next line from the conversation partner. `history` is [{role: "partner"|"learner", text}]."""
    messages = [{"role": "system", "content": system_prompt(scenario, level)}]
    for turn in history[-MAX_HISTORY:]:
        role = "assistant" if turn["role"] == "partner" else "user"
        messages.append({"role": role, "content": turn["text"]})
    for attempt in range(2):
        data = _structured_chat(messages, REPLY_SCHEMA, temperature=0.5 if attempt == 0 else 0.2)
        text = _clean_russian(data.get("reply", ""))
        if CYRILLIC.search(text) and not LATIN.search(text):
            break
        log.warning("Chat reply wasn't Russian (%r); retrying", text[:80])
    else:
        raise ChatUnavailable("The chat model didn't reply in Russian. Try again.")
    suggestions = [{"russian": _clean_russian(s.get("russian", "")), "english": s.get("english", "").strip()}
                   for s in data.get("suggestions", [])]
    suggestions = [s for s in suggestions if CYRILLIC.search(s["russian"]) and not LATIN.search(s["russian"])]
    return {"reply": text, "translation": data.get("translation", "").strip(), "suggestions": suggestions[:2]}


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s-]", " ", text.lower().replace("ё", "е")).split()


def word_diff(original: str, corrected: str) -> list[dict]:
    """Tokens of the corrected sentence marked "same" or "changed", plus removed original words."""
    a, b = _words(original), corrected.split()
    b_norm = [_words(w)[0] if _words(w) else "" for w in b]
    out: list[dict] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b_norm, autojunk=False).get_opcodes():
        if op == "equal":
            out += [{"text": w, "kind": "same"} for w in b[j1:j2]]
        else:
            out += [{"text": w, "kind": "removed"} for w in a[i1:i2]]
            out += [{"text": w, "kind": "changed"} for w in b[j1:j2]]
    return out


def check(text: str) -> dict:
    """Grammar check of one learner sentence.

    Returns {"status": "correct" | "corrected" | "skipped", "corrected", "diff"}. Heavy rewrites
    (more than half the words changed) are treated as unreliable and skipped rather than shown.
    """
    text = " ".join(text.split())
    if not CYRILLIC.search(text) or len(_words(text)) == 0:
        return {"status": "skipped", "corrected": "", "diff": []}
    data = _structured_chat([{"role": "system", "content": CHECK_SYSTEM}, {"role": "user", "content": text}],
                            CHECK_SCHEMA, temperature=0.0)
    corrected = " ".join(data.get("corrected", "").split())
    if not corrected or _words(corrected) == _words(text):
        return {"status": "correct", "corrected": "", "diff": []}
    if LATIN.search(corrected) and not LATIN.search(text):
        return {"status": "skipped", "corrected": "", "diff": []}
    similarity = SequenceMatcher(a=_words(text), b=_words(corrected)).ratio()
    if similarity < 0.5:
        return {"status": "skipped", "corrected": "", "diff": []}
    return {"status": "corrected", "corrected": corrected, "diff": word_diff(text, corrected)}
