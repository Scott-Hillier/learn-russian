"""Experiment (Phase 8): can the speech stack tell grammar minimal pairs apart?

A Direct Instruction lesson asks for one specific answer ("Я вижу ___" → "Я вижу кошку"), so the app
knows the expected answer and the likely wrong ones (кошка, кошке…). Instead of asking "is this a good
pronunciation of the expected answer?", each recording is scored against every candidate in the set
and the best one wins (forced choice).

Rules compared:
  overall    mean letter score from the existing scorer, highest wins
  likelihood CTC forced-alignment log-likelihood of the whole utterance, with accepted pronunciation
             variants (vowel reduction, devoicing) merged into each letter; highest wins
  whisper    Whisper transcript, nearest candidate by edit distance

Voices: four Silero speakers and macOS Milena saying every form (Silero follows '+' stress marks), plus
macOS Daniel (English) reading hand-written English-style spellings for a subset, as a rough stand-in
for an English accent.

Run from backend/:  .venv/bin/python -m scripts.answer_check_experiment
             .venv/bin/python -m scripts.answer_check_experiment --lessons   (check the course's own items)
             .venv/bin/python -m scripts.answer_check_experiment --lessons --from 11   (only lessons 11 on)
"""
import json
import statistics
import sys
import time
from difflib import SequenceMatcher

import numpy as np

from app.speech.asr import asr
from app.speech.pronunciation import scorer
from app.speech.tts import tts
from app.text import strip_stress, target_words
from scripts.calibrate import say, silero

# (label, candidate forms). Every form is spoken; each is scored against all forms in its set.
SETS = [
    ("acc: кошка/кошку", ["Я в+ижу к+ошку", "Я в+ижу к+ошка"]),
    ("acc: мама/маму", ["Я в+ижу м+аму", "Я в+ижу м+ама"]),
    ("acc: книга/книгу", ["Я чит+аю кн+игу", "Я чит+аю кн+ига"]),
    ("acc: вода/воду (stress moves)", ["Я пь+ю в+оду", "Я пь+ю вод+а"]),
    ("gen: нет воды", ["У мен+я нет вод+ы", "У мен+я нет вод+а"]),
    ("gen: нет брата", ["У мен+я нет бр+ата", "У мен+я нет бр+ат"]),
    ("prep: в парке", ["Я в п+арке", "Я в п+арк"]),
    ("prep: в Москве", ["Я в Москв+е", "Я в Москв+а"]),
    ("prep/acc: в школе/в школу", ["Я в шк+оле", "Я в шк+олу"]),
    ("instr: с молоком", ["К+офе с молок+ом", "К+офе с молок+о"]),
    ("plural: книга/книги", ["+Это кн+иги", "+Это кн+ига"]),
    ("plural: стол/столы", ["+Это стол+ы", "+Это ст+ол"]),
    ("poss: мой/моя/моё", ["+Это м+ой дом", "+Это мо+я дом", "+Это мо+ё дом"]),
    ("adj: новый/новая/новое", ["+Это н+овый дом", "+Это н+овая дом", "+Это н+овое дом"]),
    ("verb: читать 5 forms", ["Я чит+аю", "Я чит+аешь", "Я чит+ает", "Я чит+аем", "Я чит+ают"]),
    ("verb: говорить 3 forms", ["Он говор+ит", "Он говор+ю", "Он говор+ят"]),
    ("past: читал/читала", ["Я чит+ал", "Я чит+ала"]),
    ("pron: меня/мне", ["Мен+я зов+ут +Анна", "Мне зов+ут +Анна"]),
    ("neg: не", ["+Это не к+ошка", "+Это к+ошка"]),
    ("lexical: кошка/собака", ["+Это к+ошка", "+Это саб+ака"]),
]

# (set label, form index, English-style spelling for macOS Daniel)
ACCENT = [
    ("acc: кошка/кошку", 0, "ya vee-zhoo kosh-koo"),
    ("acc: кошка/кошку", 1, "ya vee-zhoo kosh-kah"),
    ("acc: мама/маму", 0, "ya vee-zhoo mah-moo"),
    ("acc: мама/маму", 1, "ya vee-zhoo mah-mah"),
    ("gen: нет воды", 0, "oo men-ya nyet vah-dee"),
    ("gen: нет воды", 1, "oo men-ya nyet vah-dah"),
    ("poss: мой/моя/моё", 0, "etta moy dom"),
    ("poss: мой/моя/моё", 1, "etta mah-yah dom"),
    ("poss: мой/моя/моё", 2, "etta mah-yo dom"),
    ("verb: читать 5 forms", 0, "ya chee-tah-yoo"),
    ("verb: читать 5 forms", 2, "ya chee-tah-yet"),
    ("verb: читать 5 forms", 4, "ya chee-tah-yoot"),
    ("past: читал/читала", 0, "ya chee-tahl"),
    ("past: читал/читала", 1, "ya chee-tah-lah"),
]

SILERO = ["xenia", "aidar", "baya", "eugene"]
RULES = ("overall", "likelihood", "whisper")


def overall_scores(forms: list[str], logp: np.ndarray) -> list[float]:
    out = []
    for form in forms:
        words = scorer.score(target_words(form), None, logp=logp)
        vals = [l["score"] for w in words for l in w["letters"] if l["score"] is not None]
        out.append(sum(vals) / max(1, len(vals)))
    return out


def likelihood_scores(forms: list[str], logp: np.ndarray) -> list[float]:
    return [scorer.likelihood(target_words(f), logp) for f in forms]


def norm(text: str) -> str:
    text = strip_stress(text).lower().replace("ё", "е")
    return " ".join("".join(c for c in text if c.isalpha() or c.isspace()).split())


def whisper_scores(forms: list[str], audio: np.ndarray) -> tuple[list[float], str]:
    heard = norm(asr.transcribe(audio))
    return [SequenceMatcher(a=heard, b=norm(f), autojunk=False).ratio() for f in forms], heard


def decide(scores: list[float]) -> tuple[int, float]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    margin = scores[order[0]] - scores[order[1]]
    return order[0], margin


def run(items) -> dict:
    """items: (set label, forms, spoken index, voice, audio). Returns per-rule tallies."""
    tally = {r: {"ok": 0, "n": 0, "margins_ok": [], "margins_bad": [], "by_set": {}} for r in RULES}
    timing = {r: [] for r in RULES}
    for label, forms, spoken, voice, audio in items:
        t0 = time.perf_counter(); logp = scorer.log_probs(audio); model = time.perf_counter() - t0
        t0 = time.perf_counter(); ov = overall_scores(forms, logp); timing["overall"].append(model + time.perf_counter() - t0)
        t0 = time.perf_counter(); lk = likelihood_scores(forms, logp); timing["likelihood"].append(model + time.perf_counter() - t0)
        t0 = time.perf_counter(); wh, heard = whisper_scores(forms, audio); timing["whisper"].append(time.perf_counter() - t0)
        for rule, scores in (("overall", ov), ("likelihood", lk), ("whisper", wh)):
            pick, margin = decide(scores)
            ok = pick == spoken
            t = tally[rule]
            t["ok"] += ok
            t["n"] += 1
            (t["margins_ok"] if ok else t["margins_bad"]).append(margin)
            s = t["by_set"].setdefault(label, [0, 0])
            s[0] += ok
            s[1] += 1
            if not ok:
                extra = f' heard "{heard}"' if rule == "whisper" else ""
                print(f"  ✗ {rule:10s} {label:30s} [{voice}] said {strip_stress(forms[spoken])!r} "
                      f"→ picked {strip_stress(forms[pick])!r}{extra}")
    for r in RULES:
        tally[r]["seconds"] = statistics.mean(timing[r])
    return tally


def report(name: str, tally: dict) -> None:
    print(f"\n== {name} ==")
    labels = list(tally["overall"]["by_set"])
    print(f"{'set':32s}" + "".join(f"{r:>12s}" for r in RULES))
    for label in labels:
        row = "".join(f"{tally[r]['by_set'][label][0]:>8d}/{tally[r]['by_set'][label][1]:<3d}" for r in RULES)
        print(f"{label:32s}{row}")
    for r in RULES:
        t = tally[r]
        print(f"{r:10s} {t['ok']}/{t['n']} = {100 * t['ok'] / t['n']:.1f}%   "
              f"mean time {t['seconds'] * 1000:.0f} ms   "
              f"margin when right: median {statistics.median(t['margins_ok']) if t['margins_ok'] else 0:.3f}, "
              f"when wrong: max {max(t['margins_bad']) if t['margins_bad'] else 0:.3f}")


def lesson_items(first: int = 1) -> int:
    """Every speaking item in the course, as the app checks it: each answer said by native voices must be
    accepted, and each distractor said instead must be rejected."""
    from app.course import lessons
    from app.speech.answers import check_answer

    ok = total = 0
    seen = set()
    for lesson in lessons():
        if lesson["id"] < first:
            continue
        for e_idx, ex in enumerate(lesson["exercises"]):
            for item in ex["items"]:
                key = (item.get("answer"), tuple(item.get("accept", [])), tuple(item.get("distractors", [])))
                if "answer" not in item or key in seen:  # review exercises repeat earlier items
                    continue
                seen.add(key)
                for spoken in [item["answer"], *item.get("distractors", [])]:
                    expect = spoken == item["answer"]
                    for spk in ("xenia", "aidar"):
                        result = check_answer(item["answer"], item.get("accept", []), item.get("distractors", []),
                                              silero(spoken, spk))
                        good = result["correct"] == expect
                        ok += good
                        total += 1
                        if not good:
                            print(f"  ✗ lesson {lesson['id']} ex {e_idx + 1}: answer {strip_stress(item['answer'])!r} "
                                  f"[{spk}] said {strip_stress(spoken)!r} → correct={result['correct']} "
                                  f"score={result['score']} heard={result['heard']} reason={result['reason']}")
    print(f"lesson items: {ok}/{total} judged as expected")
    return 0


def main() -> int:
    tts.load()
    scorer.load()
    if "--lessons" in sys.argv:
        first = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 1
        return lesson_items(first)
    asr.warm_up()
    native = []
    for label, forms in SETS:
        for i, form in enumerate(forms):
            for spk in SILERO:
                native.append((label, forms, i, spk, silero(form, spk)))
            native.append((label, forms, i, "Milena", say(strip_stress(form), "Milena")))
    native_tally = run(native)

    sets = dict(SETS)
    accent = [(label, sets[label], i, "Daniel", say(spelling, "Daniel")) for label, i, spelling in ACCENT]
    accent_tally = run(accent)

    report(f"Native voices ({len(native)} recordings)", native_tally)
    report(f"English voice, English-style spellings ({len(accent)} recordings)", accent_tally)
    if "--json" in sys.argv:
        print(json.dumps({"native": native_tally, "accent": accent_tally}, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
