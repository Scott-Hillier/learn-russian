"""Checking a spoken answer in a lesson: did the learner say the expected answer, or something else?

The lesson knows the expected answer and the likely wrong ones (distractors: other words in the set, the
wrong case ending…). One model pass scores the recording against every candidate, and the candidate with
the highest whole-utterance likelihood is what we take them to have said (forced choice). See
scripts/answer_check_experiment.py and PLAN.md for how well this tells grammar forms apart.

The candidates are scored in learner mode: sounds an English speaker commonly uses instead of a Russian one
(ы → и, щ → ш, х → к, no ь softness) count towards the answer, since a lesson asks *which* answer was said.
If that would make the answer and a distractor sound the same (был / бил), the strict spelling is used.

The check is for the right words, not good pronunciation (the learner's call, 2026-10-27: learning many
words matters more than saying a few perfectly). The letter scores only colour the feedback. Forced choice
alone would accept anything closer to the answer than to the distractors, including a different sentence
altogether, so the answer must also roughly fit the audio: its forced alignment can't fall far below the
model's own unsteered reading (MIN_FIT, per 2 s of audio). A wrong answer that only just beats the right
one (TIE_MARGIN) is a near tie, and the learner gets the benefit of the doubt.

The thresholds come from scripts/learner_benchmark.py: every course item said by native voices and by
simulated learners (slow, pausing, sounding out, wrong stress, English-speaker substitutions, a heavy English
accent), through a laptop mic and Opus, against its closest distractor and against an unrelated sentence.
"""
from difflib import SequenceMatcher

import numpy as np

from ..text import display_stress, normalize_words, target_words
from .compare import build_feedback
from .pronunciation import learner_form, scorer

MIN_FIT = -55  # how far (log-likelihood per 100 frames) the answer may fall below the free reading and still count
TIE_MARGIN = 1.0  # a wrong answer winning by less than this (per 100 frames) is a near tie: counted as right
HEARD_MATCH = 0.7  # how closely a wrong candidate must match the model's unsteered reading to be named


def _plain(text: str) -> str:
    return " ".join(normalize_words(text))


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
    feedback = build_feedback(answer, "", letters)
    won = said_answer or -gap < TIE_MARGIN
    correct = won and fit >= MIN_FIT
    # Why a miss was a miss, so the learner isn't left with green letters and a red verdict:
    # "other": another answer fitted better; "fit": the answer's sounds were there, but so was more (or less).
    reason = None if correct else "other" if not won else "fit"
    heard = None
    if not won:
        # Forced choice always names the closest candidate. Only report it when the model's own unsteered
        # reading of the audio agrees, so "дом" said for "Это собака" isn't reported as "Собака".
        free = scorer.greedy_text(logp)
        if SequenceMatcher(a=_plain(candidates[best]), b=free, autojunk=False).ratio() >= HEARD_MATCH:
            heard = display_stress(candidates[best])
    return {
        "correct": correct,
        "reason": reason,
        "silent": False,
        "heard": heard,
        "score": feedback["score"],
        "words": feedback["words"],
    }
