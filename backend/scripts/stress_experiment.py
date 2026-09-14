"""Experiment (not used by the app): can word stress be judged automatically from acoustics?

Method: align letters with the pronunciation model, measure each vowel's region (halfway to its
neighbouring letters): duration, peak intensity and median pitch, z-score them within the word, and
call the most prominent vowel "stressed" if it beats the runner-up by a margin.

Test: 211 stress-marked Starter words spoken by two Silero voices with the correct stress and with
the stress moved to a neighbouring vowel (Silero follows '+' marks).

Result (2026-09-14): with settings that leave ≥90% of correctly stressed words unflagged, only ~42%
of moved-stress words were caught (best balanced: 70% / 75%). Comparing against the native voice's
own prominence pattern was worse (25% caught), and a syllable-nucleus (intensity peak) detector was
no better (42%) and failed to find all syllables in 18% of recordings. That's not reliable enough to
tell a learner their stress is wrong, so the app shows pitch contours instead.

Run from backend/:  .venv/bin/python -m scripts.stress_experiment
"""
import itertools
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

from app import config
from app.speech.audio import SAMPLE_RATE
from app.speech.pronunciation import scorer
from app.speech.tts import tts
from app.text import strip_stress
from scripts.calibrate import silero

VOWELS = set("аеёиоуыэюя")
EDGE = 0.12  # seconds of context before the first / after the last letter
WEIGHTS = {"duration": 0.2, "intensity": 0.2, "pitch": 0.6}  # best found
CONFIDENT_MARGIN = 1.2


def _tracks(pcm: np.ndarray):
    import parselmouth

    snd = parselmouth.Sound(pcm.astype(np.float64), sampling_frequency=SAMPLE_RATE)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=75.0, pitch_ceiling=500.0)
    f0 = pitch.selected_array["frequency"]
    f0 = np.where(f0 > 0, f0, np.nan)
    intensity = snd.to_intensity(minimum_pitch=75.0, time_step=0.01)
    return (np.asarray(pitch.xs()), f0), (np.asarray(intensity.xs()), intensity.values[0])


def _semitones(f0: np.ndarray) -> np.ndarray:
    voiced = f0[~np.isnan(f0)]
    return 12 * np.log2(f0 / np.median(voiced)) if voiced.size else f0


def vowel_measurements(words: list[dict], pcm: np.ndarray) -> list[list[dict]]:
    """Per word, per aligned vowel: letter index, region and acoustic measurements."""
    (pt, f0), (it, db) = _tracks(pcm)
    st = _semitones(f0)
    duration = pcm.size / SAMPLE_RATE
    timeline = [(wi, li, l["t"]) for wi, w in enumerate(words) for li, l in enumerate(w["letters"])
                if l.get("t") is not None]
    out: list[list[dict]] = [[] for _ in words]
    for g, (wi, li, t) in enumerate(timeline):
        if words[wi]["letters"][li]["char"].lower() not in VOWELS:
            continue
        start = (timeline[g - 1][2] + t) / 2 if g > 0 else max(0.0, t - EDGE)
        end = (t + timeline[g + 1][2]) / 2 if g + 1 < len(timeline) else min(duration, t + EDGE)
        in_i = (it >= start) & (it <= end)
        in_p = (pt >= start) & (pt <= end) & ~np.isnan(st)
        out[wi].append({
            "index": li,
            "start": start, "end": end,
            "duration": end - start,
            "intensity": float(np.max(db[in_i])) if in_i.any() else math.nan,
            "pitch": float(np.median(st[in_p])) if in_p.any() else math.nan,
        })
    return out


def _z(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=float)
    valid = ~np.isnan(arr)
    if valid.sum() < 2 or np.nanstd(arr) < 1e-9:
        return [0.0] * len(values)
    z = (arr - np.nanmean(arr)) / np.nanstd(arr)
    return [0.0 if math.isnan(v) else float(v) for v in z]


def judge_stress(vowels: list[dict], weights: dict = WEIGHTS, margin: float = CONFIDENT_MARGIN) -> tuple[int, bool] | None:
    """(letter index of the most prominent vowel, whether the margin is large enough to trust)."""
    if len(vowels) < 2:
        return None
    cues = {k: _z([v[k] for v in vowels]) for k in weights}
    prominence = [sum(weights[k] * cues[k][i] for k in weights) for i in range(len(vowels))]
    order = np.argsort(prominence)[::-1]
    confident = prominence[order[0]] - prominence[order[1]] >= margin
    return vowels[order[0]]["index"], confident


def stress_detection() -> None:
    """Native voices saying multi-vowel words with correct stress, and with the stress moved.

    Grid-searches cue weights and the confidence margin, reporting for each setting:
    - correct: correct-stress audio judged ok (or not confident) — we must not nag good speakers
    - caught: moved-stress audio confidently flagged as wrong
    """
    data = json.loads((config.DATA_DIR / "decks" / "starter_words.json").read_text(encoding="utf-8"))
    words = [ru for u in data["units"] for ru, _ in u["cards"]
             if "+" in ru and " " not in ru and sum(c in VOWELS for c in ru.lower()) >= 2]
    cache = Path(tempfile.gettempdir()) / "learn-russian-stress-samples.json"
    if cache.exists():
        samples = json.loads(cache.read_text())
    else:
        samples = []  # {word, expected, measurements: {voice: {"correct": [...], "moved": [...]}}}
        for word in words:
            plain = strip_stress(word)
            vowel_pos = [i for i, c in enumerate(plain.lower()) if c in VOWELS]
            expected = word.index("+")  # '+' precedes the vowel, so its index is the vowel's plain index
            wrong_vowel = next(v for v in sorted(vowel_pos, key=lambda v: abs(v - expected)) if v != expected)
            moved = plain[:wrong_vowel] + "+" + plain[wrong_vowel:]
            entry = {"word": word, "expected": expected, "m": {}}
            for voice in ("xenia", "aidar"):
                for kind, spoken in (("correct", word), ("moved", moved)):
                    audio = silero(spoken, voice)
                    measured = vowel_measurements(scorer.score([word], audio), audio)[0]
                    entry["m"].setdefault(voice, {})[kind] = measured if len(measured) == len(vowel_pos) else None
            samples.append(entry)
        cache.write_text(json.dumps(samples))
    print(f"stress samples: {len(samples)} words (cached at {cache})")

    def evaluate(method, weights, margin):
        ok_correct = caught = n = 0
        for s in samples:
            for ref_voice, test_voice in (("xenia", "aidar"), ("aidar", "xenia")):
                ref, m = s["m"][ref_voice]["correct"], s["m"][test_voice]
                if not ref or not m["correct"] or not m["moved"]:
                    continue
                n += 1
                for kind in ("correct", "moved"):
                    detected, confident = judge_stress(m[kind], weights, margin)
                    target = s["expected"] if method == "absolute" else judge_stress(ref, weights, 0)[0]
                    flagged = detected != target and confident
                    if kind == "correct":
                        ok_correct += not flagged
                    else:
                        caught += flagged
        return ok_correct / n, caught / n

    for method in ("absolute", "reference"):
        best = None
        for dur, inten, margin in itertools.product((0.2, 0.4, 0.6, 0.8), (0.0, 0.2, 0.4, 0.6), (0.0, 0.25, 0.5, 0.8, 1.2)):
            if dur + inten > 1:
                continue
            weights = {"duration": dur, "intensity": inten, "pitch": round(1 - dur - inten, 2)}
            spec, sens = evaluate(method, weights, margin)
            if spec >= 0.9 and (best is None or sens > best[1]):
                best = (spec, sens, weights, margin)
        if best:
            print(f"{method}: best with ≥90% correct-ok → correct-ok {best[0]:.0%}, moved-caught {best[1]:.0%}, "
                  f"weights {best[2]}, margin {best[3]}")
        else:
            print(f"{method}: no setting reaches 90% correct-ok")


if __name__ == "__main__":
    tts.load()
    scorer.load()
    stress_detection()
    sys.exit(0)
