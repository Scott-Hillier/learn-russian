import json
import re

import numpy as np

from app import config, progress
from app.flashcards import needs_stress_mark
from app.speech.audio import SAMPLE_RATE, voiced_bounds, voiced_duration
from app.text import strip_stress, target_words

SENTENCES = json.loads((config.DATA_DIR / "sentences.json").read_text(encoding="utf-8"))
PAIRS = json.loads((config.DATA_DIR / "minimal_pairs.json").read_text(encoding="utf-8"))
BAD_STRESS = re.compile(r"\+(?![аеёиоуыэюяАЕЁИОУЫЭЮЯ])")


def test_sentences_are_well_formed():
    count = 0
    for theme in SENTENCES["themes"]:
        for s in theme["sentences"]:
            count += 1
            text = " ".join(s["text"].replace("|", " ").split())
            words = target_words(text)
            assert len(words) == len(s["glosses"]), f"glosses don't match words in {text}"
            assert not BAD_STRESS.search(text), text
            assert not needs_stress_mark(re.sub(r"[^\w\s+]", " ", text)), f"missing stress mark in {text}"
            chunks = [target_words(c) for c in s["text"].split("|")]
            assert all(chunks) and sum(chunks, []) == words, f"bad chunks in {s['text']}"
            assert s["english"].strip()
    assert count >= 30


def test_minimal_pairs_differ_by_one_sound():
    for group in PAIRS["groups"]:
        assert group["pairs"] and group["explanation"]
        for pair in group["pairs"]:
            a, b = pair["a"][0], pair["b"][0]
            for w in (a, b):
                assert not BAD_STRESS.search(w) and not needs_stress_mark(w), w
            pa, pb = strip_stress(a), strip_stress(b)
            assert pa != pb
            # same length with one differing letter, or one extra soft sign
            if len(pa) == len(pb):
                assert sum(x != y for x, y in zip(pa, pb)) == 1, (pa, pb)
            else:
                assert pb.replace("ь", "") == pa or pa.replace("ь", "") == pb, (pa, pb)
            differing = {x for x, y in zip(pa, pb) if x != y} | {y for x, y in zip(pa, pb) if x != y}
            assert differing <= set(group["letters"]) or group["id"] == "soft-sign", (group["id"], pa, pb)


def test_voiced_duration_ignores_leading_and_trailing_silence():
    tone = 0.3 * np.sin(np.linspace(0, 2 * np.pi * 220, SAMPLE_RATE)).astype(np.float32)  # 1 s
    silence = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
    audio = np.concatenate([silence, tone, silence, tone, silence])
    assert abs(voiced_duration(audio) - 2.5) < 0.05
    assert voiced_duration(np.zeros(1000, dtype=np.float32)) == 0.0


def test_voiced_bounds_skip_key_clicks():
    rng = np.random.default_rng(0)
    tone = 0.3 * np.sin(np.linspace(0, 2 * np.pi * 220, SAMPLE_RATE)).astype(np.float32)  # 1 s of "speech"
    click = np.zeros(int(0.03 * SAMPLE_RATE), dtype=np.float32)
    click[:80] = 0.6 * rng.standard_normal(80)
    gap = np.zeros(int(0.4 * SAMPLE_RATE), dtype=np.float32)
    # Space pressed to start, speech, Space pressed to stop.
    audio = np.concatenate([gap, click, gap, tone, gap, click, gap])
    start, end = voiced_bounds(audio)
    assert abs(start / SAMPLE_RATE - 0.83) < 0.03 and abs(end / SAMPLE_RATE - 1.83) < 0.03
    # A stop consonant's short silence inside a word doesn't split off its release.
    release = np.concatenate([tone[: SAMPLE_RATE // 2], gap[: int(0.15 * SAMPLE_RATE)], click])
    assert abs(voiced_bounds(release)[1] / SAMPLE_RATE - (0.5 + 0.15 + 0.01)) < 0.03
    # A single short sound is still speech when there's nothing longer.
    assert voiced_bounds(np.concatenate([gap, click, gap])) is not None


def test_best_scores(tmp_path):
    db = tmp_path / "p.db"
    for score in (40, 90, 70):
        progress.record_attempt("sentence", "Где метр+о?", {"score": score, "words": []}, path=db)
    progress.record_attempt("phrase", "Где метр+о?", {"score": 100, "words": []}, path=db)
    assert progress.best_scores("sentence", path=db) == {"Где метр+о?": 90}
