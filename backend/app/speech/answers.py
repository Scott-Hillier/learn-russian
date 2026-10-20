"""Checking a spoken answer in a lesson: did the learner say the expected answer, or something else?

The lesson knows the expected answer and the likely wrong ones (distractors: other words in the set, the
wrong case ending…). One model pass scores the recording against every candidate, and the candidate with
the highest whole-utterance likelihood is what we take them to have said (forced choice). See
scripts/answer_check_experiment.py and PLAN.md for how well this tells grammar forms apart.

The candidates are scored in learner mode: sounds an English speaker commonly uses instead of a Russian one
(ы → и, щ → ш, х → к, no ь softness) count towards the answer, since a lesson asks *which* answer was said.
If that would make the answer and a distractor sound the same (был / бил), the strict spelling is used.

Forced choice alone would accept anything closer to the answer than to the distractors, including a
different sentence altogether, so the answer must also fit the audio: its forced alignment can't fall far
below the model's own unsteered reading (FIT, per 2 s of audio), and its letter score must reach MIN_SCORE.
A borderline fit, or a wrong answer that only just beats the right one, asks the learner to say it again
instead of marking it wrong.

The thresholds come from scripts/learner_benchmark.py: every course item said by native voices and by
simulated learners (slow, pausing, sounding out, wrong stress, English-speaker substitutions, a heavy English
accent), through a laptop mic and Opus, against its closest distractor and against an unrelated sentence.
"""
from difflib import SequenceMatcher

import numpy as np

from ..text import display_stress, normalize_words, target_words
from .compare import build_feedback
from .pronunciation import learner_form, scorer

MIN_SCORE = 30  # learner-mode letter score (0–100) the expected answer needs as well as winning the forced choice
MIN_FIT = -40  # how far (log-likelihood per 100 frames) the answer may fall below the free reading and still count
AGAIN_FIT = -55  # between this and MIN_FIT: unclear, so the learner is asked to say it again
AGAIN_MARGIN = 2.5  # a wrong answer winning by less than this (per 100 frames) is too close to call: ask again
HEARD_MATCH = 0.7  # how closely a wrong candidate must match the model's unsteered reading to be named


def _plain(text: str) -> str:
    return " ".join(normalize_words(text))


def _overall(words: list[dict]) -> int:
    vals = [l["score"] for w in words for l in w["letters"] if l["score"] is not None]
    return round(100 * sum(vals) / len(vals)) if vals else 100


def check_answer(answer: str, accept: list[str], distractors: list[str], pcm: np.ndarray) -> dict:
    logp = scorer.log_probs(pcm)
    candidates = [answer, *accept, *distractors]
    right = {learner_form(c) for c in [answer, *accept]}
    learner = not right & {learner_form(d) for d in distractors}
    likelihoods = [scorer.likelihood(target_words(c), logp, learner=learner) for c in candidates]
    best = int(np.argmax(likelihoods))
    said_answer = best <= len(accept)
    per_100 = 100 / max(1, logp.shape[0])
    best_right = max(likelihoods[:len(accept) + 1])
    fit = (best_right - scorer.free_likelihood(logp)) * per_100
    gap = (best_right - max(likelihoods[len(accept) + 1:], default=-np.inf)) * per_100
    letters = scorer.score(target_words(answer), pcm, logp=logp)  # strict: the feedback shows every slip
    gate = _overall(scorer.score(target_words(answer), pcm, logp=logp, learner=True)) if learner else _overall(letters)
    feedback = build_feedback(answer, "", letters)
    correct = said_answer and gate >= MIN_SCORE and fit >= MIN_FIT
    again = fit >= AGAIN_FIT and ((said_answer and not correct and gate >= MIN_SCORE)
                                  or (not said_answer and -gap < AGAIN_MARGIN))
    heard = None
    if not said_answer:
        # Forced choice always names the closest candidate. Only report it when the model's own unsteered
        # reading of the audio agrees, so "дом" said for "Это собака" isn't reported as "Собака".
        free = scorer.greedy_text(logp)
        if SequenceMatcher(a=_plain(candidates[best]), b=free, autojunk=False).ratio() >= HEARD_MATCH:
            heard = display_stress(candidates[best])
    return {
        "correct": correct,
        "again": again,
        "silent": False,
        "heard": heard,
        "score": feedback["score"],
        "words": feedback["words"],
    }
