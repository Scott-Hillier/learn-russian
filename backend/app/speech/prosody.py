"""Intonation from acoustics, using Praat (parselmouth).

Automatic word-stress verdicts were tried and rejected (see scripts/stress_experiment.py): they caught
under half of misplaced stress while wrongly flagging ~1 in 11 correct words. Instead the app shows the
learner's pitch contour over the native one, with the native stressed syllables marked, so learners
can see where the voice rises, falls and emphasises.
"""
import numpy as np

from .audio import SAMPLE_RATE

POINTS = 60


def _pitch(pcm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Times (s) and pitch in semitones relative to the speaker's median (NaN when unvoiced)."""
    import parselmouth

    snd = parselmouth.Sound(pcm.astype(np.float64), sampling_frequency=SAMPLE_RATE)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=75.0, pitch_ceiling=500.0)
    f0 = pitch.selected_array["frequency"]
    f0 = np.where(f0 > 0, f0, np.nan)
    voiced = f0[~np.isnan(f0)]
    semitones = 12 * np.log2(f0 / np.median(voiced)) if voiced.size else f0
    return np.asarray(pitch.xs()), semitones


def pitch_contour(pcm: np.ndarray, points: int = POINTS) -> dict | None:
    """Contour resampled over the voiced span: {"values": [semitones | None], "start", "end"} in seconds.

    Unvoiced points are None so a chart can draw gaps. Normalising per speaker lets a learner's
    contour be compared with a native voice with a different pitch range.
    """
    times, st = _pitch(pcm)
    voiced = np.where(~np.isnan(st))[0]
    if voiced.size < 3:
        return None
    start, end = float(times[voiced[0]]), float(times[voiced[-1]])
    values: list[float | None] = []
    for t in np.linspace(start, end, points):
        i = int(np.argmin(np.abs(times - t)))
        values.append(None if np.isnan(st[i]) else round(float(st[i]), 2))
    return {"values": values, "start": start, "end": end}


def stress_marks(words: list[dict], contour: dict) -> list[dict]:
    """Positions (0–1 along the contour) of stressed vowels, from the scorer's letter alignment."""
    span = contour["end"] - contour["start"]
    marks = []
    for w in words:
        vowels = [l for l in w["letters"] if l["char"].lower() in "аеёиоуыэюя"]
        if len(vowels) < 2:
            continue  # one-syllable words carry no useful stress mark
        for l in w["letters"]:
            if l["stressed"] and l.get("t") is not None and span > 0:
                position = (l["t"] - contour["start"]) / span
                if 0 <= position <= 1:
                    marks.append({"position": round(position, 3), "label": l["char"].lower()})
    return marks
