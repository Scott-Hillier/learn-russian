"""Word-level comparison between the target phrase and what Whisper heard."""
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from ..text import display_stress, normalize_words

CLOSE_RATIO = 0.75


@dataclass
class WordResult:
    target: str          # target word as displayed (with stress accent)
    heard: str | None    # what was recognised in its place
    status: str          # correct | close | wrong | missing


def _display_words(target: str) -> list[str]:
    """Split the target into display words, one per normalised word (hyphenated words split)."""
    out = []
    for raw in target.replace("-", " - ").split():
        if raw == "-":
            continue
        if normalize_words(raw):
            out.append(display_stress(raw).strip(".,!?;:«»\"…"))
    return out


def compare(target: str, heard: str) -> dict:
    t_norm = normalize_words(target)
    h_norm = normalize_words(heard)
    t_disp = _display_words(target)
    if len(t_disp) != len(t_norm):  # defensive: fall back to normalised words for display
        t_disp = t_norm

    words: list[WordResult] = []
    extra: list[str] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=t_norm, b=h_norm, autojunk=False).get_opcodes():
        if op == "equal":
            words += [WordResult(t_disp[i], h_norm[j], "correct") for i, j in zip(range(i1, i2), range(j1, j2))]
        elif op == "delete":
            words += [WordResult(t_disp[i], None, "missing") for i in range(i1, i2)]
        elif op == "insert":
            extra += h_norm[j1:j2]
        else:  # replace: pair up words in order, leftovers are missing/extra
            for k in range(max(i2 - i1, j2 - j1)):
                i, j = i1 + k, j1 + k
                if i < i2 and j < j2:
                    ratio = SequenceMatcher(a=t_norm[i], b=h_norm[j]).ratio()
                    words.append(WordResult(t_disp[i], h_norm[j], "close" if ratio >= CLOSE_RATIO else "wrong"))
                elif i < i2:
                    words.append(WordResult(t_disp[i], None, "missing"))
                else:
                    extra.append(h_norm[j])

    points = {"correct": 1.0, "close": 0.6, "wrong": 0.0, "missing": 0.0}
    raw = sum(points[w.status] for w in words) / max(1, len(words))
    score = max(0.0, raw - 0.15 * len(extra))
    return {
        "words": [asdict(w) for w in words],
        "extra": extra,
        "score": round(score * 100),
        "tips": _tips(words, extra, heard),
    }


def _tips(words: list[WordResult], extra: list[str], heard: str) -> list[str]:
    if not heard.strip():
        return ["I didn't catch anything. Check your mic level and speak a little louder and closer."]
    tips = []
    for w in words:
        if w.status == "close":
            tips.append(f"“{w.target}” was almost right (heard “{w.heard}”). Listen to it slowly and copy the vowels.")
        elif w.status == "wrong":
            tips.append(f"“{w.target}” sounded like “{w.heard}”. Play the slow version and try just that word.")
        elif w.status == "missing":
            tips.append(f"I didn't hear “{w.target}”. Make sure every word is spoken clearly.")
    if extra:
        tips.append(f"I heard extra words: {' '.join(extra)}.")
    if not tips:
        tips.append("Every word was recognised. Nice! Try the normal speed and match the rhythm.")
    return tips[:4]
