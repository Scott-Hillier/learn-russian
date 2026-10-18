"""Checking a spoken answer in a lesson: did the learner say the expected answer, or something else?

The lesson knows the expected answer and the likely wrong ones (distractors: other words in the set, the
wrong case ending…). One model pass scores the recording against every candidate, and the candidate with
the highest whole-utterance likelihood is what we take them to have said (forced choice). See
scripts/answer_check_experiment.py and PLAN.md for how well this tells grammar forms apart.

Forced choice alone would accept anything closer to the answer than to the distractors, including
mumbling, so the expected answer must also reach MIN_SCORE on the letter-level pronunciation score.
"""
from difflib import SequenceMatcher

import numpy as np

from ..text import display_stress, normalize_words, target_words
from .compare import build_feedback
from .pronunciation import scorer

MIN_SCORE = 50  # letter-level score (0–100) the expected answer needs as well as winning the forced choice
HEARD_MATCH = 0.7  # how closely a wrong candidate must match the model's unsteered reading to be named


def _plain(text: str) -> str:
    return " ".join(normalize_words(text))


def check_answer(answer: str, accept: list[str], distractors: list[str], pcm: np.ndarray) -> dict:
    logp = scorer.log_probs(pcm)
    candidates = [answer, *accept, *distractors]
    likelihoods = [scorer.likelihood(target_words(c), logp) for c in candidates]
    best = int(np.argmax(likelihoods))
    feedback = build_feedback(answer, "", scorer.score(target_words(answer), pcm, logp=logp))
    said_answer = best <= len(accept)
    heard = None
    if not said_answer:
        # Forced choice always names the closest candidate. Only report it when the model's own unsteered
        # reading of the audio agrees, so "дом" said for "Это собака" isn't reported as "Собака".
        free = scorer.greedy_text(logp)
        if SequenceMatcher(a=_plain(candidates[best]), b=free, autojunk=False).ratio() >= HEARD_MATCH:
            heard = display_stress(candidates[best])
    return {
        "correct": said_answer and feedback["score"] >= MIN_SCORE,
        "silent": False,
        "heard": heard,
        "score": feedback["score"],
        "words": feedback["words"],
    }
