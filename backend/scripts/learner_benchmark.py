"""Benchmark: does the lesson answer checker treat a *learner's* voice fairly?

Real learner recordings can't tell us what the right pronunciation is, and native test voices are too clean,
so this simulates the ways a beginner's speech differs, for every speaking item in the course:

  native     Silero voices and macOS Milena (the baseline)
  slow       Silero at x-slow speed
  pauses     each word said separately with a pause between (searching for the next word)
  syllables  words sounded out syllable by syllable (no vowel reduction, every syllable stressed)
  stress     the stress put on the wrong syllable
  accent     typical English-speaker substitutions: ы → и, щ → ш, х → к, no ь softness
  english    English voices reading an English-style respelling ("ya vee-zhoo kosh-koo"): a heavy accent

Every recording goes through a random laptop "channel" (level, background noise, room echo, mic EQ) and then
Opus compression, as the browser's recorder does. For each item three things are said: the answer (must be
accepted), the closest wrong answer from its distractors (must be rejected), and an unrelated answer from
another lesson (must be rejected).

  collect   synthesise, run the model once per recording and save every score the decision rules need
  analyse   replay decision rules (strict vs learner mode, letter-score floor, "say it again" band) on the
            saved scores and report accept/reject rates per condition

Run from backend/ (don't run the app server at the same time on 8 GB):
  .venv/bin/python -m scripts.learner_benchmark collect --out <scratch>/bench.json
  .venv/bin/python -m scripts.learner_benchmark analyse <scratch>/bench.json
"""
import argparse
import json
import random
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import soundfile as sf

from app.speech.audio import SAMPLE_RATE, decode_to_pcm16k, trim_and_pad
from app.speech.pronunciation import learner_form, scorer
from app.speech.tts import tts
from app.text import strip_stress, target_words

VOWELS = set("аеёиоуыэюя")
SILERO_VOICES = ["xenia", "aidar", "baya", "eugene", "kseniya"]
ENGLISH_VOICES = ["Samantha", "Daniel", "Karen", "Moira", "Rishi", "Tessa", "Eddy (English (US))",
                  "Flo (English (UK))", "Reed (English (US))", "Shelley (English (UK))", "Sandy (English (US))",
                  "Grandpa (English (UK))"]
CONDITIONS = ["native", "slow", "pauses", "syllables", "stress", "accent", "english"]


# ---------- text transforms ----------

def _letters(word: str) -> list[tuple[str, bool]]:
    """(letter, stressed) for a word with '+' marks; a one-vowel word is stressed."""
    out, pending = [], False
    for ch in word:
        if ch == "+":
            pending = True
            continue
        low = ch.lower()
        out.append((low, (pending and low in VOWELS) or low == "ё"))
        if low in VOWELS:
            pending = False
    vowels = [i for i, (c, _) in enumerate(out) if c in VOWELS]
    if len(vowels) == 1:
        out[vowels[0]] = (out[vowels[0]][0], True)
    return out


def _syllables(letters: list) -> list[list]:
    """Split letters into syllables: each vowel ends one; of a consonant cluster, the first goes back."""
    vowels = [i for i, (c, _) in enumerate(letters) if c in VOWELS]
    if len(vowels) < 2:
        return [letters]
    cuts = []
    for a, b in zip(vowels, vowels[1:]):
        between = b - a - 1
        cuts.append(a + 1 + (1 if between >= 2 else 0))
    out, start = [], 0
    for c in cuts:
        out.append(letters[start:c])
        start = c
    out.append(letters[start:])
    return out


def wrong_stress(text: str) -> str:
    words = []
    for w in target_words(text):
        letters = _letters(w)
        vowels = [i for i, (c, _) in enumerate(letters) if c in VOWELS and c != "ё"]
        stressed = [i for i, (_, s) in enumerate(letters) if s]
        if len(vowels) < 2 or not stressed:
            words.append(w)
            continue
        others = [i for i in vowels if i != stressed[0]]
        new = others[0] if others[0] > stressed[0] or len(others) == 1 else others[-1]
        words.append("".join(("+" if i == new else "") + c for i, (c, _) in enumerate(letters)))
    return " ".join(words)


def sounded_out(text: str) -> str:
    return " ".join(" ".join("".join(c for c, _ in syl) for syl in _syllables(_letters(w)))
                    for w in target_words(text))


def accented(text: str) -> str:
    out = strip_stress(text).lower()
    for a, b in (("ы", "и"), ("щ", "ш"), ("х", "к"), ("ь", ""), ("ъ", "")):
        out = out.replace(a, b)
    return out


_CONS = {"б": "b", "в": "v", "г": "g", "д": "d", "ж": "zh", "з": "z", "й": "y", "к": "k", "л": "l", "м": "m",
         "н": "n", "п": "p", "р": "r", "с": "s", "т": "t", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
         "щ": "sh", "ь": "", "ъ": ""}
_VOW = {"а": ("ah", "uh"), "о": ("oh", "uh"), "у": ("oo", "oo"), "ы": ("ih", "ih"), "и": ("ee", "ee"),
        "э": ("eh", "eh"), "ё": ("yo", "yo"), "ю": ("yoo", "yoo"), "я": ("yah", "yuh")}


def english_spelling(text: str) -> str:
    """How an English speaker might write a Russian phrase down to read it: "Я вижу кошку" → "yah vee-zhoo kosh-koo"."""
    words = []
    for w in target_words(text):
        letters = _letters(w)
        sylls = []
        for syl in _syllables(letters):
            out, prev = [], None
            for i, (c, stressed) in enumerate(syl):
                if c == "е":
                    out.append("eh" if prev in ("ж", "ш", "ц") else "yeh" if stressed else "ee" if prev else "yee")
                elif c in _VOW:
                    out.append(_VOW[c][0 if stressed else 1])
                else:
                    out.append(_CONS.get(c, ""))
                prev = c
            sylls.append("".join(out))
        words.append("-".join(s for s in sylls if s))
    return " ".join(words)


# ---------- audio ----------

def _to16k(path: str) -> np.ndarray:
    return decode_to_pcm16k(Path(path).read_bytes())


def silero(text: str, voice: str, rate: str | None = None) -> np.ndarray:
    from xml.sax.saxutils import escape

    kwargs = dict(speaker=voice, sample_rate=48000, put_accent=True, put_yo=True)
    if rate:
        audio = tts._model.apply_tts(ssml_text=f'<speak><prosody rate="{rate}">{escape(text)}</prosody></speak>',
                                     **kwargs)
    else:
        audio = tts._model.apply_tts(text=text, **kwargs)
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        sf.write(f.name, audio.numpy(), 48000)
        return _to16k(f.name)


def say(text: str, voice: str, rate: int | None = None) -> np.ndarray:
    with tempfile.NamedTemporaryFile(suffix=".aiff") as f:
        subprocess.run(["say", "-v", voice, *(["-r", str(rate)] if rate else []), "-o", f.name, text], check=True)
        return _to16k(f.name)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def speak(text: str, condition: str, rng: random.Random) -> tuple[np.ndarray, str]:
    """Clean 16 kHz audio of `text` spoken in a condition, and the voice used."""
    voice = rng.choice(SILERO_VOICES)
    if condition == "native":
        if rng.random() < 0.2:
            return say(strip_stress(text), "Milena"), "Milena"
        return silero(text, voice), voice
    if condition == "slow":
        return silero(text, voice, "x-slow"), voice
    if condition == "pauses":
        parts = []
        for w in target_words(text):
            parts += [silero(w, voice), _silence(rng.uniform(0.3, 0.8))]
        return np.concatenate(parts[:-1]), voice
    if condition == "syllables":
        return silero(sounded_out(text), voice, "slow"), voice
    if condition == "stress":
        return silero(wrong_stress(text), voice), voice
    if condition == "accent":
        return silero(accented(text), voice), voice
    if condition == "english":
        voice = rng.choice(ENGLISH_VOICES)
        return say(english_spelling(text), voice, rate=rng.choice([140, 160, 180])), voice
    raise ValueError(condition)


def _smooth(x: np.ndarray, n: int) -> np.ndarray:
    return np.convolve(x, np.ones(n) / n, mode="same").astype(np.float32)


def channel(audio: np.ndarray, rng: random.Random) -> np.ndarray:
    """A laptop recording: silence around the speech, then random level, EQ, echo and noise, then Opus."""
    nprng = np.random.default_rng(rng.randrange(1 << 30))
    x = np.concatenate([_silence(rng.uniform(0.2, 0.6)), audio, _silence(rng.uniform(0.3, 0.8))])
    x = x / (np.abs(x).max() + 1e-9)
    if rng.random() < 0.5:  # cheap mic: less bass and less treble
        x = x - _smooth(x, 80)
        x = _smooth(x, 3)
    if rng.random() < 0.4:  # small room
        n = int(rng.uniform(0.15, 0.35) * SAMPLE_RATE)
        ir = nprng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n) * 0.3
        ir[0] = 1.0
        x = np.convolve(x, ir)[: x.size].astype(np.float32)
    speech_rms = np.sqrt(np.mean(audio ** 2)) / (np.abs(audio).max() + 1e-9)
    if rng.random() < 0.6:  # fan / room noise
        snr = rng.uniform(10, 25)
        noise = _smooth(nprng.standard_normal(x.size).astype(np.float32), 4)
        noise *= speech_rms / (np.sqrt(np.mean(noise ** 2)) + 1e-9) / (10 ** (snr / 20))
        x = x + noise
    x = (x / (np.abs(x).max() + 1e-9) * rng.uniform(0.15, 0.9)).astype(np.float32)
    proc = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "f32le", "-ar", str(SAMPLE_RATE),
                           "-ac", "1", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-f", "webm", "pipe:1"],
                          input=x.tobytes(), capture_output=True, check=True)
    return decode_to_pcm16k(proc.stdout)


# ---------- collect ----------

def course_items() -> list[dict]:
    from app.course import lessons

    items, seen = [], set()
    for lesson in lessons():
        for ex in lesson["exercises"]:
            if ex["type"] not in ("teach", "say", "dialogue"):
                continue
            for item in ex["items"]:
                if "answer" in item and item["answer"] not in seen:
                    seen.add(item["answer"])
                    items.append({"lesson": lesson["id"], "answer": item["answer"],
                                  "accept": item.get("accept", []), "distractors": item.get("distractors", [])})
    return items


def _plain(text: str) -> str:
    return " ".join(strip_stress(text).lower().replace("ё", "е").split())


def features(item: dict, pcm: np.ndarray) -> dict:
    candidates = [item["answer"], *item["accept"], *item["distractors"]]
    logp = scorer.log_probs(pcm)
    out = {"frames": int(logp.shape[0]), "free": scorer.free_likelihood(logp), "greedy": scorer.greedy_text(logp)}
    for mode, learner in (("strict", False), ("learner", True)):
        out[mode] = {
            "lik": [scorer.likelihood(target_words(c), logp, learner=learner) for c in candidates],
            "score": _overall(scorer.score(target_words(item["answer"]), None, logp=logp, learner=learner)),
        }
    return out


def _overall(words: list[dict]) -> int:
    vals = [l["score"] for w in words for l in w["letters"] if l["score"] is not None]
    return round(100 * sum(vals) / len(vals)) if vals else 100


def collect(args) -> int:
    rng = random.Random(args.seed)
    tts.load()
    scorer.load()
    items = all_items = course_items()
    if args.limit:
        items = rng.sample(items, min(args.limit, len(items)))
    conditions = args.conditions.split(",") if args.conditions else CONDITIONS
    print(f"{len(items)} items × {len(conditions)} conditions × 3 recordings", flush=True)
    records = []
    t0 = time.time()
    for n, item in enumerate(items):
        answers = {_plain(t) for t in [item["answer"], *item["accept"]]}
        hardest = max(item["distractors"], default=None,
                      key=lambda d: SequenceMatcher(a=_plain(item["answer"]), b=_plain(d)).ratio())
        others = [i["answer"] for i in all_items if _plain(i["answer"]) not in answers
                  and all(_plain(i["answer"]) != _plain(d) for d in item["distractors"])]
        other = rng.choice(others)
        item["learner_safe"] = len({learner_form(c) for c in [item["answer"], *item["accept"]]}
                                   & {learner_form(d) for d in item["distractors"]}) == 0
        for condition in conditions:
            for kind, text in (("answer", item["answer"]), ("distractor", hardest), ("other", other)):
                if text is None:
                    continue
                clean, voice = speak(text, condition, rng)
                pcm = trim_and_pad(channel(clean, rng))
                records.append({"item": n, "lesson": item["lesson"], "condition": condition, "kind": kind,
                                "said": text, "voice": voice, **features(item, pcm)})
        if n % 5 == 4:
            done = (n + 1) / len(items)
            print(f"  {n + 1}/{len(items)} items, {(time.time() - t0) / done * (1 - done) / 60:.0f} min left",
                  flush=True)
    Path(args.out).write_text(json.dumps({"items": items, "records": records}, ensure_ascii=False))
    print(f"saved {len(records)} recordings to {args.out}")
    return 0


# ---------- analyse ----------

def fit(item: dict, rec: dict, mode: str) -> float:
    """How far the best right answer's forced alignment falls short of the model's free reading, per 100
    frames (2 s): about 0 when the answer was said, far below when something else was."""
    lik = rec[mode]["lik"]
    return (max(lik[:1 + len(item["accept"])]) - rec["free"]) / max(1, rec["frames"]) * 100


def decide(item: dict, rec: dict, mode: str, min_score: int, margin: float, again_from: int,
           min_fit: float = -1e9, again_fit: float | None = None) -> str:
    """'right', 'wrong' or 'again' (unclear: ask the learner to say it again, nothing is counted).

    Right: a right answer wins the forced choice by at least `margin`, with a letter score of at least
    min_score and a fit of at least min_fit. again: a right answer won but only reached again_from (score)
    or again_fit (fit), or a wrong answer won by less than `margin`.
    """
    m = mode if (mode == "strict" or item["learner_safe"]) else "strict"
    lik = rec[m]["lik"]
    n_ok = 1 + len(item["accept"])
    best = int(np.argmax(lik))
    best_ok = max(lik[:n_ok])
    best_wrong = max(lik[n_ok:], default=-np.inf)
    score = rec[m]["score"]
    f = fit(item, rec, m)
    again_fit = min_fit if again_fit is None else again_fit
    gap = (best_ok - best_wrong) / max(1, rec["frames"]) * 100  # per 100 frames (2 s), so length doesn't matter
    if best < n_ok:
        if score >= min_score and gap >= margin and f >= min_fit:
            return "right"
        if score >= again_from and f >= again_fit:
            return "again"
        return "wrong"
    if -gap < margin and score >= min_score:
        return "again"
    return "wrong"


def table(data: dict, mode: str, min_score: int, margin: float, uncertain_score: int, show: bool = True,
          min_fit: float = -1e9, again_fit: float | None = None) -> dict:
    items = data["items"]
    rows: dict[tuple[str, str], dict[str, int]] = {}
    for rec in data["records"]:
        verdict = decide(items[rec["item"]], rec, mode, min_score, margin, uncertain_score, min_fit, again_fit)
        cell = rows.setdefault((rec["condition"], rec["kind"]), {"right": 0, "wrong": 0, "again": 0})
        cell[verdict] += 1
    conditions = [c for c in CONDITIONS if (c, "answer") in rows]
    summary = {}
    if show:
        print(f"\n== mode={mode} min_score={min_score} margin={margin} again_from={uncertain_score} "
              f"min_fit={min_fit} again_fit={again_fit} ==")
        print(f"{'condition':11s} {'answer accepted':>17s} {'again':>7s} {'distractor rejected':>21s} "
              f"{'again':>7s} {'other rejected':>16s}")
    for c in conditions:
        a, d, o = rows[(c, "answer")], rows.get((c, "distractor")), rows[(c, "other")]
        pct = lambda cell, k: 100 * cell[k] / max(1, sum(cell.values()))
        summary[c] = {"accept": pct(a, "right"), "answer_again": pct(a, "again"),
                      "reject": 100 - pct(d, "right") if d else 100.0, "dist_again": pct(d, "again") if d else 0,
                      "other_reject": 100 - pct(o, "right")}
        if show:
            s = summary[c]
            print(f"{c:11s} {s['accept']:16.1f}% {s['answer_again']:6.1f}% {s['reject']:20.1f}% "
                  f"{s['dist_again']:6.1f}% {s['other_reject']:15.1f}%")
    return summary


def analyse(args) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    unsafe = sum(not i["learner_safe"] for i in data["items"])
    print(f"{len(data['records'])} recordings, {len(data['items'])} items "
          f"({unsafe} items fall back to strict in learner mode)")
    table(data, "strict", 50, 0, 50)  # the checker as shipped
    if args.grid:
        print("\nGrid (learner-like conditions = all except native and english):")
        learnerish = ["slow", "pauses", "syllables", "stress", "accent"]
        for mode in ("strict", "learner"):
            for min_score in (0, 20, 30, 40, 50):
                for margin in (0, 0.5, 1, 2):
                    s = table(data, mode, min_score, margin, min_score, show=False)
                    avg = lambda k, cs: sum(s[c][k] for c in cs if c in s) / len([c for c in cs if c in s])
                    print(f"{mode:8s} score≥{min_score:<3d} margin {margin:<4} "
                          f"native acc {s['native']['accept']:5.1f} rej {s['native']['reject']:5.1f} | "
                          f"learner acc {avg('accept', learnerish):5.1f} again {avg('answer_again', learnerish):4.1f} "
                          f"rej {avg('reject', learnerish):5.1f} other-rej {avg('other_reject', learnerish):5.1f} | "
                          f"english acc {s['english']['accept']:5.1f} rej {s['english']['reject']:5.1f}")
    if args.fit_grid:
        print("\nFit grid (learner-like conditions = all except native and english):")
        learnerish = ["slow", "pauses", "syllables", "stress", "accent"]
        for mode in ("strict", "learner"):
            for min_score in (0, 30, 40, 50):
                for min_fit in (-15, -20, -25, -30, -40):
                    for again_fit in (None, min_fit - 15):
                        s = table(data, mode, min_score, 0, min_score, show=False, min_fit=min_fit, again_fit=again_fit)
                        avg = lambda k, cs: sum(s[c][k] for c in cs) / len(cs)
                        print(f"{mode:8s} score≥{min_score:<3d} fit≥{min_fit:<4} again≥{str(again_fit):5s} "
                              f"native acc {s['native']['accept']:5.1f} other-rej {s['native']['other_reject']:5.1f} | "
                              f"learner acc {avg('accept', learnerish):5.1f} again {avg('answer_again', learnerish):4.1f} "
                              f"rej {avg('reject', learnerish):5.1f} other-rej {avg('other_reject', learnerish):5.1f} | "
                              f"english acc {s['english']['accept']:5.1f} again {s['english']['answer_again']:4.1f} "
                              f"other-rej {s['english']['other_reject']:5.1f}")
    rule = lambda spec: [t(v) for t, v in zip((str, int, float, int, float, float), spec.split(":"))]
    for spec in args.rule or []:
        mode, min_score, margin, again, *fits = rule(spec)
        table(data, mode, min_score, margin, again, True, *fits)
    if args.misses:
        mode, min_score, margin, again, *fits = rule(args.misses)
        items = data["items"]
        for rec in data["records"]:
            v = decide(items[rec["item"]], rec, mode, min_score, margin, again, *fits)
            bad = (rec["kind"] == "answer" and v == "wrong") or (rec["kind"] != "answer" and v == "right")
            if bad:
                m = rec["learner" if mode == "learner" else "strict"]
                print(f"  ✗ {rec['condition']:9s} {rec['kind']:10s} answer {strip_stress(items[rec['item']]['answer'])!r}"
                      f" said {strip_stress(rec['said'])!r} [{rec['voice']}] score {m['score']} "
                      f"fit {fit(items[rec['item']], rec, mode):.1f} heard {rec['greedy']!r}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--out", required=True)
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--conditions", default="")
    a = sub.add_parser("analyse")
    a.add_argument("file")
    a.add_argument("--grid", action="store_true")
    a.add_argument("--fit-grid", action="store_true")
    a.add_argument("--rule", action="append",
                   help="mode:min_score:margin:again_from[:min_fit[:again_fit]], e.g. learner:40:0:40:-25:-40")
    a.add_argument("--misses", help="list misjudged recordings under a rule (same format as --rule)")
    args = p.parse_args()
    return collect(args) if args.cmd == "collect" else analyse(args)


if __name__ == "__main__":
    sys.exit(main())
