import numpy as np

from app.speech import prosody
from app.speech.audio import SAMPLE_RATE


def _glide(f_start: float, f_end: float, seconds: float = 1.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    freq = np.linspace(f_start, f_end, t.size)
    return (0.3 * np.sin(2 * np.pi * np.cumsum(freq) / SAMPLE_RATE)).astype(np.float32)


def test_rising_pitch_contour_rises():
    contour = prosody.pitch_contour(_glide(150, 250))
    values = [v for v in contour["values"] if v is not None]
    assert len(contour["values"]) == prosody.POINTS and len(values) > 40
    assert values[-1] - values[0] > 6  # 150 → 250 Hz is about 8.8 semitones


def test_silence_has_no_contour():
    assert prosody.pitch_contour(np.zeros(SAMPLE_RATE, dtype=np.float32)) is None


def test_stress_marks_positions_and_skips_monosyllables():
    contour = {"start": 1.0, "end": 2.0, "values": []}
    words = [
        {"letters": [{"char": "м", "stressed": False, "t": 1.1}, {"char": "о", "stressed": False, "t": 1.2},
                     {"char": "л", "stressed": False, "t": 1.3}, {"char": "о", "stressed": False, "t": 1.4},
                     {"char": "к", "stressed": False, "t": 1.6}, {"char": "о", "stressed": True, "t": 1.75}]},
        {"letters": [{"char": "д", "stressed": False, "t": 1.85}, {"char": "а", "stressed": True, "t": 1.9}]},
    ]
    assert prosody.stress_marks(words, contour) == [{"position": 0.75, "label": "о"}]
