"""Letter-level pronunciation scoring ("goodness of pronunciation", GOP).

A Russian wav2vec2 CTC model (trained to output Cyrillic letters, with no language model) gives
per-frame letter probabilities. We force-align the target spelling to the audio with CTC
Viterbi, then measure for each letter how much of the model's belief in that segment went to
that letter (or an acceptable variant). A low score plus the strongest competing letter tells us,
for example, that "ы" sounded like "и".

Because the model maps sound to spelling, natural Russian reductions (unstressed о → "а",
final devoicing б → "п", silent в in "здравствуйте") are accepted as variants, not errors.
"""
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import config
from ..text import display_stress

log = logging.getLogger(__name__)

FRAME_SECONDS = 0.02  # wav2vec2 emits one frame per 320 samples at 16 kHz
GOOD = 0.5   # letter probability share at or above this is pronounced well
CLOSE = 0.15  # between CLOSE and GOOD is "almost"
# Below this average letter probability (the rest is "no letter" / silence) the model didn't hear any clear
# letter where this one should be, so naming the strongest competitor would be a guess from noise.
MIN_HEARD_MASS = 0.5

VOWELS = set("аеёиоуыэюя")
VOICED_TO_VOICELESS = {"б": "п", "в": "ф", "г": "к", "д": "т", "ж": "ш", "з": "с"}
VOICELESS_TO_VOICED = {v: k for k, v in VOICED_TO_VOICELESS.items()}
VOICELESS = set("пфктшсхцчщ")
VOICING_TRIGGERS = set("бгджз")  # в does not voice the consonant before it
UNSTRESSED_CLITICS = {"не", "ни", "по", "до", "на", "за", "из", "от", "без", "под", "над", "про",
                      "и", "а", "но", "же", "ли", "бы", "у", "о", "об"}
REDUCTION_VARIANTS = {"о": {"а"}, "а": {"о"}, "е": {"и", "я"}, "я": {"и", "е"}, "э": {"и", "е"}}
# (cluster, offset within cluster) of letters that are not pronounced
SILENT_CLUSTERS = [("вств", 0), ("здн", 1), ("стн", 1), ("лнц", 0), ("рдц", 1), ("стл", 1), ("ться", 2)]
WORD_EXCEPTIONS = {
    "пожалуйста": {"silent": [5, 6]},       # usually "пожалста"
    "что": {"alts": {0: {"ш"}}},
    "чтобы": {"alts": {0: {"ш"}}},
    "конечно": {"alts": {4: {"ш"}}},
    "скучно": {"alts": {3: {"ш"}}},
    "сегодня": {"alts": {2: {"в"}}},
    "его": {"alts": {1: {"в"}}},
}


@dataclass
class Letter:
    char: str                 # letter as written (case and ё preserved)
    norm: str                 # model token: lowercase, ё → е
    stressed: bool = False
    alts: set[str] = field(default_factory=set)
    silent: bool = False


def analyse_word(raw: str) -> list[Letter]:
    """Turn a word with '+' stress marks into letters with pronunciation variants."""
    letters: list[Letter] = []
    pending = False
    for ch in raw:
        if ch == "+":
            pending = True
            continue
        low = ch.lower()
        letters.append(Letter(ch, "е" if low == "ё" else low, stressed=(pending and low in VOWELS) or low == "ё"))
        if low in VOWELS:
            pending = False

    plain = "".join(l.norm for l in letters)
    vowels = [l for l in letters if l.norm in VOWELS]
    stress_known = any(l.stressed for l in letters)
    if not stress_known and len(vowels) == 1 and plain not in UNSTRESSED_CLITICS:
        vowels[0].stressed = stress_known = True

    for i, l in enumerate(letters):
        c = l.norm
        if c in VOWELS and not l.stressed:
            l.alts |= REDUCTION_VARIANTS.get(c, set())
            if c == "и" and i + 1 < len(letters) and letters[i + 1].norm in "яею":
                l.alts.add("ь")  # -ия is said like -ья
        if c in "еэ":
            l.alts.add("э" if c == "е" else "е")
        if c == "и" and i > 0 and letters[i - 1].norm in "жшц":
            l.alts.add("ы")  # ж, ш, ц are always hard: жизнь, цирк → "жызнь", "цырк"
        j = i + 1
        while j < len(letters) and letters[j].norm in "ьъ":
            j += 1
        after = letters[j].norm if j < len(letters) else ""
        if c in VOICED_TO_VOICELESS and (after == "" or after in VOICELESS):
            l.alts.add(VOICED_TO_VOICELESS[c])
        if c in VOICELESS_TO_VOICED and after in VOICING_TRIGGERS:
            l.alts.add(VOICELESS_TO_VOICED[c])
        if i > 0 and c == letters[i - 1].norm and c not in VOWELS:
            l.silent = True  # doubled consonant: one long sound
        if c == "г" and after in ("к", "ч"):
            l.alts.add("х")

    for cluster, offset in SILENT_CLUSTERS:
        for m in re.finditer(cluster, plain):
            letters[m.start() + offset].silent = True
    for m in re.finditer("тс|тьс", plain):  # -тся / -ться → "ца"
        letters[m.start()].alts.add("ц")
        letters[m.end() - 1].alts.add("ц")
    for m in re.finditer("[сз]ч", plain):
        letters[m.start()].alts |= {"щ", "ш"}
        letters[m.start() + 1].alts.add("щ")
    if len(plain) > 3 and re.search("[ое]го$", plain):  # genitive -ого/-его: г → "в"
        letters[-2].alts.add("в")
    exc = WORD_EXCEPTIONS.get(plain, {})
    for idx in exc.get("silent", []):
        letters[idx].silent = True
    for idx, alts in exc.get("alts", {}).items():
        letters[idx].alts |= alts
    return letters


def ctc_align(logp: np.ndarray, tokens: list[int], blank: int = 0) -> list[list[int]] | None:
    """CTC Viterbi forced alignment. Returns the frames assigned to each token, or None."""
    T, L = logp.shape[0], len(tokens)
    S = 2 * L + 1
    if L == 0 or T < L:
        return None
    ext = np.full(S, blank)
    ext[1::2] = tokens
    emit = logp[:, ext]
    can_skip = np.zeros(S, dtype=bool)
    can_skip[3::2] = ext[3::2] != ext[1:-2:2]

    dp = np.full(S, -np.inf)
    dp[0], dp[1] = emit[0, 0], emit[0, 1]
    back = np.zeros((T, S), dtype=np.int8)
    ninf = np.array([-np.inf])
    for t in range(1, T):
        prev1 = np.concatenate([ninf, dp[:-1]])
        prev2 = np.concatenate([ninf, ninf, dp[:-2]])
        prev2[~can_skip] = -np.inf
        stacked = np.stack([dp, prev1, prev2])
        back[t] = stacked.argmax(0)
        dp = stacked.max(0) + emit[t]

    s = S - 1 if dp[S - 1] >= dp[S - 2] else S - 2
    if not np.isfinite(dp[s]):
        return None
    frames: list[list[int]] = [[] for _ in tokens]
    for t in range(T - 1, -1, -1):
        if s % 2 == 1:
            frames[s // 2].append(t)
        s -= back[t, s]
    return [f[::-1] for f in frames]


class PronunciationScorer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._vocab: dict[str, int] = {}
        self._inv: dict[int, str] = {}
        self.loaded = False

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            import torch
            from huggingface_hub import snapshot_download
            from transformers import Wav2Vec2ForCTC

            patterns = ["*.json", "pytorch_model.bin"]
            try:
                path = snapshot_download(config.PRONUNCIATION_MODEL, allow_patterns=patterns, local_files_only=True)
            except Exception:
                log.info("Downloading pronunciation model (one-time)…")
                path = snapshot_download(config.PRONUNCIATION_MODEL, allow_patterns=patterns)
            self._vocab = json.loads((Path(path) / "vocab.json").read_text(encoding="utf-8"))
            self._inv = {i: c for c, i in self._vocab.items()}
            torch.set_num_threads(4)
            self._model = Wav2Vec2ForCTC.from_pretrained(path).eval()
            self.loaded = True

    def _log_probs(self, audio: np.ndarray) -> np.ndarray:
        import torch

        x = (audio - audio.mean()) / (audio.std() + 1e-7)
        with torch.inference_mode():
            logits = self._model(torch.from_numpy(x.astype(np.float32))[None]).logits[0]
            return torch.log_softmax(logits.float(), dim=-1).numpy()

    def score(self, words: list[str], audio: np.ndarray) -> list[dict]:
        """Score each target word (with '+' stress marks) letter by letter."""
        self.load()
        with self._lock:
            logp = self._log_probs(audio)

        analysed = [analyse_word(w) for w in words]
        sep = self._vocab["|"]
        tokens, owners = [], []  # owners: (word index, letter index) or None for separators
        for wi, letters in enumerate(analysed):
            idxs = [li for li, l in enumerate(letters) if l.norm in self._vocab]
            if not idxs:
                continue
            if tokens:
                tokens.append(sep)
                owners.append(None)
            for li in idxs:
                tokens.append(self._vocab[letters[li].norm])
                owners.append((wi, li))
        frames = ctc_align(logp, tokens) if tokens else None

        probs = np.exp(logp)
        first_letter = self._vocab["а"]  # letters а…я are the contiguous tail of the vocab
        letter_mass = probs[:, first_letter:].sum(-1) + 1e-9
        results: dict[tuple[int, int], tuple[float, str | None]] = {}
        centers: dict[tuple[int, int], float] = {}  # seconds: where each letter was aligned in the audio
        for k, owner in enumerate(owners):
            if owner is None:
                continue
            if frames is not None and frames[k]:
                centers[owner] = round((float(np.mean(frames[k])) + 0.5) * FRAME_SECONDS, 3)
            letter = analysed[owner[0]][owner[1]]
            ok_ids = [self._vocab[c] for c in {letter.norm} | letter.alts if c in self._vocab]
            if frames is None or not frames[k]:
                results[owner] = (0.0, None)
                continue
            fr = frames[k]
            share = float(probs[fr][:, ok_ids].sum() / letter_mass[fr].sum())
            competitors = probs[fr][:, first_letter:].sum(0)
            competitors[[i - first_letter for i in ok_ids]] = 0
            clear = float(letter_mass[fr].mean()) >= MIN_HEARD_MASS
            heard = self._inv[int(competitors.argmax()) + first_letter] if clear else None
            results[owner] = (share, heard)

        out = []
        for wi, (raw, letters) in enumerate(zip(words, analysed)):
            letter_out, scores = [], []
            for li, l in enumerate(letters):
                if (wi, li) not in results or l.silent:
                    status, heard, value = ("silent" if l.silent else "unscored"), None, None
                else:
                    share, heard = results[(wi, li)]
                    status = "good" if share >= GOOD else "close" if share >= CLOSE else "wrong"
                    value = round(min(1.0, share / GOOD), 3)
                    scores.append(value)
                    if status == "good":
                        heard = None
                letter_out.append({"char": l.char, "stressed": l.stressed, "status": status,
                                   "heard_as": heard, "score": value, "t": centers.get((wi, li))})
            out.append({
                "text": raw,
                "display": display_stress(raw),
                "score": round(100 * sum(scores) / len(scores)) if scores else 100,
                "letters": letter_out,
            })
        return out


scorer = PronunciationScorer()
