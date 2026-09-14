"""Combine word recognition (Whisper) and letter-level pronunciation scores into feedback."""
from difflib import SequenceMatcher

from ..text import display_stress, normalize_words, strip_stress, target_words
from .tips import letter_tip

CLOSE_RATIO = 0.75
WORD_GOOD = 85
WORD_CLOSE = 55


def recognise_words(target: str, heard: str) -> tuple[list[dict], list[str]]:
    """Align target words with the transcript. Returns per-word {heard, recognized} and extra words."""
    t_norm = [" ".join(normalize_words(w)) for w in target_words(target)]
    h_norm = normalize_words(heard)
    words: list[dict] = []
    extra: list[str] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=t_norm, b=h_norm, autojunk=False).get_opcodes():
        if op == "equal":
            words += [{"heard": h_norm[j], "recognized": "correct"} for j in range(j1, j2)]
        elif op == "delete":
            words += [{"heard": None, "recognized": "missing"} for _ in range(i1, i2)]
        elif op == "insert":
            extra += h_norm[j1:j2]
        else:  # replace: pair words in order; leftovers are missing / extra
            for k in range(max(i2 - i1, j2 - j1)):
                i, j = i1 + k, j1 + k
                if i < i2 and j < j2:
                    ratio = SequenceMatcher(a=t_norm[i], b=h_norm[j]).ratio()
                    words.append({"heard": h_norm[j], "recognized": "close" if ratio >= CLOSE_RATIO else "wrong"})
                elif i < i2:
                    words.append({"heard": None, "recognized": "missing"})
                else:
                    extra.append(h_norm[j])
    return words, extra


def build_feedback(target: str, heard: str, pronunciation: list[dict] | None) -> dict:
    raw_words = target_words(target)
    recognition, extra = recognise_words(target, heard)
    nothing_heard = not heard.strip() and pronunciation is None

    words = []
    for i, raw in enumerate(raw_words):
        rec = recognition[i]
        if pronunciation:
            p = pronunciation[i]
            score, letters = p["score"], p["letters"]
        else:  # no acoustic scoring available: fall back to recognition only
            score = {"correct": 100, "close": 60}.get(rec["recognized"], 0)
            letters = [{"char": c, "stressed": False, "status": "unscored", "heard_as": None}
                       for c in strip_stress(raw)]
        if nothing_heard:
            status = "missing"
        elif score >= WORD_GOOD:
            status = "good"
        elif score >= WORD_CLOSE:
            status = "close"
        else:
            status = "missing" if rec["recognized"] == "missing" and score < 30 else "wrong"
        words.append({"text": raw, "display": display_stress(raw), "score": score, "status": status,
                      "letters": letters, **rec})

    weights = [max(1, sum(l["status"] in ("good", "close", "wrong") for l in w["letters"])) for w in words]
    overall = round(sum(w["score"] * n for w, n in zip(words, weights)) / max(1, sum(weights)))
    if nothing_heard:
        overall = 0
    return {"heard": heard, "score": overall, "words": words, "extra": extra,
            "tips": _tips(words, extra, nothing_heard)}


def _tips(words: list[dict], extra: list[str], nothing_heard: bool) -> list[str]:
    if nothing_heard:
        return ["I didn't catch anything. Check your mic level, then speak a little louder and closer."]
    # Priority: missing words, then specific advice for wrong sounds, then generic/"almost" tips.
    tips: list[tuple[int, str]] = []
    seen: set[str] = set()
    for w in words:
        plain = strip_stress(w["text"])
        if w["status"] == "missing":
            tips.append((0, f"I didn't hear “{plain}”. Make sure every word is spoken clearly."))
            continue
        for l in w["letters"]:
            if l["status"] not in ("wrong", "close") or l["char"].lower() in seen:
                continue
            seen.add(l["char"].lower())
            text, specific = letter_tip(plain, l)
            tips.append(((1 if l["status"] == "wrong" else 3) + (0 if specific else 1), text))
    if extra:
        tips.append((5, f"I also heard extra words: {' '.join(extra)}."))
    if not tips:
        return ["Every sound was clear. Great job! Now try matching the native speed and rhythm."]
    return [t for _, t in sorted(tips, key=lambda t: t[0])][:4]
