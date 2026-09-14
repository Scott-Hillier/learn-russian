"""Calibrate pronunciation scoring with synthetic speech.

Native voices (Silero speakers + macOS Milena) reading every starter phrase should score high;
deliberate mispronunciations should flag the right letter; an English voice reading
transliterations should score clearly lower.

Run from backend/:  .venv/bin/python -m scripts.calibrate
"""
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf

from app import config
from app.speech.audio import decode_to_pcm16k, trim_and_pad
from app.speech.pronunciation import scorer
from app.speech.tts import tts
from app.text import strip_stress, target_words

SILERO_SPEAKERS = ["xenia", "aidar", "baya", "eugene"]

# (target, what is actually said, letter that should be flagged)
MISPRONUNCIATIONS = [
    ("М+ышка", "М+ишка", "ы"),
    ("Был", "Бил", "ы"),
    ("Мать", "Мат", "ь"),
    ("Сп+ать", "Сп+ат", "ь"),
    ("Щ+ука", "Ш+ука", "щ"),
    ("Вы", "Ви", "ы"),
    ("Дом", "Том", "Д"),
    ("Хлеб", "Клеб", "Х"),
    ("Р+ыба", "Л+ыба", "Р"),
    ("Сын", "Сон", "ы"),
]

# (target, English-voice spelling)
ENGLISH_ACCENT = [
    ("Прив+ет", "pree-vet"),
    ("Хорош+о", "ho-ro-show"),
    ("Я не поним+аю", "yah nee pon-ee-my-oo"),
    ("Вы говор+ите по-англ+ийски?", "vee go-vo-ree-tay po ang-lee-skee"),
    ("Д+обрый в+ечер", "doh-bree vetch-er"),
    ("Спас+ибо", "spa-see-bow"),
]


def silero(text: str, speaker: str):
    audio = tts._model.apply_tts(text=text, speaker=speaker, sample_rate=48000, put_accent=True, put_yo=True)
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        sf.write(f.name, audio.numpy(), 48000)
        return trim_and_pad(decode_to_pcm16k(Path(f.name).read_bytes()))


def say(text: str, voice: str):
    with tempfile.NamedTemporaryFile(suffix=".aiff") as f:
        subprocess.run(["say", "-v", voice, "-o", f.name, text], check=True)
        return trim_and_pad(decode_to_pcm16k(Path(f.name).read_bytes()))


def score(target: str, audio) -> tuple[int, list[str]]:
    words = scorer.score(target_words(target), audio)
    letters = sum(len([l for l in w["letters"] if l["status"] in ("good", "close", "wrong")]) for w in words)
    total = sum(w["score"] * max(1, len([l for l in w["letters"] if l["status"] in ("good", "close", "wrong")]))
                for w in words) / max(1, letters)
    flagged = [f"{strip_stress(w['text'])}:{l['char']}→{l['heard_as']}({l['status']})"
               for w in words for l in w["letters"] if l["status"] in ("wrong", "close")]
    return round(total), flagged


def alphabet_items() -> None:
    data = json.loads((config.DATA_DIR / "alphabet.json").read_text(encoding="utf-8"))
    # Only real words are scored in the app; isolated syllables are listen-only because the model
    # is unreliable on them (native TTS syllables averaged well below words).
    texts = []
    for letter in data["letters"]:
        texts += [ex["text"] for ex in letter["examples"]]
    for lesson in data["lessons"]:
        texts += [w["text"] for w in lesson["words"]]
    texts = list(dict.fromkeys(texts))
    scores = []
    for text in texts:
        for spk in ("xenia", "aidar"):
            s, flagged = score(text, silero(text, spk))
            scores.append(s)
            if s < 85:
                print(f"  {strip_stress(text)} [{spk}] {s}% flagged {flagged}")
    print(f"alphabet items: {len(texts)} texts, mean {statistics.mean(scores):.1f}%  "
          f"≥85%: {sum(s >= 85 for s in scores)}/{len(scores)}")


def contrast_letters(target: str, other: str) -> list[int]:
    """Indices (in the stress-stripped target) of letters that differ from the other word."""
    from difflib import SequenceMatcher
    t, o = strip_stress(target).lower(), strip_stress(other).lower()
    idx = []
    for op, i1, i2, _, _ in SequenceMatcher(a=t, b=o, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            idx += range(i1, i2)
    return idx


def minimal_pairs() -> None:
    """For each pair, the contrast letter must score well for the right word and be flagged for the other."""
    data = json.loads((config.DATA_DIR / "minimal_pairs.json").read_text(encoding="utf-8"))
    voices = [("silero", "xenia"), ("silero", "aidar"), ("say", "Milena")]
    ok_total = checks_total = 0
    for group in data["groups"]:
        for pair in group["pairs"]:
            words = [pair["a"][0], pair["b"][0]]
            for target, other in (words, words[::-1]):
                idx = contrast_letters(target, other)
                if not idx:  # e.g. мат vs мать: target has no letter to check
                    continue
                for kind, voice in voices:
                    def contrast_score(spoken):
                        audio = silero(spoken, voice) if kind == "silero" else say(strip_stress(spoken), voice)
                        letters = scorer.score([target], audio)[0]["letters"]
                        return min(letters[i]["score"] if letters[i]["score"] is not None else 1.0 for i in idx)
                    same, cross = contrast_score(target), contrast_score(other)
                    ok = same >= 0.99 and cross < 0.99
                    ok_total += ok
                    checks_total += 1
                    if not ok:
                        print(f"  ✗ {group['id']}: target {strip_stress(target)} [{voice}] "
                              f"same={same:.2f} said-{strip_stress(other)}={cross:.2f}")
    print(f"minimal pairs: {ok_total}/{checks_total} checks discriminate")


def sentence_items() -> None:
    """Full sentences, chunks and practice words (3+ letters) with two native voices."""
    data = json.loads((config.DATA_DIR / "sentences.json").read_text(encoding="utf-8"))
    groups: dict[str, list[str]] = {"sentences": [], "chunks": [], "words": []}
    for theme in data["themes"]:
        for s in theme["sentences"]:
            groups["sentences"].append(" ".join(s["text"].replace("|", " ").split()))
            chunks = [c.strip() for c in s["text"].split("|")]
            if len(chunks) > 1:
                groups["chunks"] += chunks
            groups["words"] += [w for w in target_words(s["text"].replace("|", " ")) if len(strip_stress(w)) >= 3]
    for name, texts in groups.items():
        texts = list(dict.fromkeys(texts))
        scores = []
        for text in texts:
            for spk in ("xenia", "aidar"):
                s, flagged = score(text, silero(text, spk))
                scores.append(s)
                if s < 85:
                    print(f"  {strip_stress(text)} [{spk}] {s}% flagged {flagged}")
        print(f"{name}: {len(texts)} texts, mean {statistics.mean(scores):.1f}%  "
              f"≥85%: {sum(s >= 85 for s in scores)}/{len(scores)}")


def main() -> int:
    tts.load()
    scorer.load()
    if "--sentences" in sys.argv:
        sentence_items()
        return 0
    if "--alphabet" in sys.argv:
        alphabet_items()
        return 0
    if "--pairs" in sys.argv:
        minimal_pairs()
        return 0
    phrases = json.loads((config.DATA_DIR / "phrases.json").read_text(encoding="utf-8"))

    print("== Native speech ==")
    native = []
    for p in phrases:
        row = []
        for spk in SILERO_SPEAKERS:
            s, flagged = score(p["text"], silero(p["text"], spk))
            row.append(s)
            if flagged:
                print(f"  {strip_stress(p['text'])} [{spk}] {s}% flagged {flagged}")
        s, flagged = score(p["text"], say(strip_stress(p["text"]), "Milena"))
        row.append(s)
        if flagged:
            print(f"  {strip_stress(p['text'])} [Milena] {s}% flagged {flagged}")
        native += row
    print(f"native: mean {statistics.mean(native):.1f}%  min {min(native)}%  "
          f"≥85%: {sum(s >= 85 for s in native)}/{len(native)}")

    print("\n== Deliberate mispronunciations ==")
    caught = 0
    for target, spoken, letter in MISPRONUNCIATIONS:
        s, flagged = score(target, silero(spoken, "aidar"))
        hit = any(f.split(":")[1].lower().startswith(letter.lower()) for f in flagged)
        caught += hit
        print(f"  {'✓' if hit else '✗'} {strip_stress(target)} said as {strip_stress(spoken)}: {s}% {flagged}")
    print(f"caught: {caught}/{len(MISPRONUNCIATIONS)}")

    print("\n== English accent (macOS Daniel) ==")
    accent = []
    for target, spelling in ENGLISH_ACCENT:
        s, flagged = score(target, say(spelling, "Daniel"))
        accent.append(s)
        print(f"  {strip_stress(target)}: {s}% {flagged}")
    print(f"accent: mean {statistics.mean(accent):.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
