"""Russian text helpers.

Stress is written Silero-style: a '+' immediately before the stressed vowel, e.g. "прив+ет".
"""
import re
import unicodedata

VOWELS = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
COMBINING_ACUTE = "́"

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "'", "э": "e", "ю": "yu",
    "я": "ya",
}
_ACUTE = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "y": "ý"}


def strip_stress(text: str) -> str:
    return text.replace("+", "").replace(COMBINING_ACUTE, "")


def display_stress(text: str) -> str:
    """"прив+ет" -> "приве́т" (combining acute accent after the stressed vowel)."""
    out = []
    pending = False
    for ch in text:
        if ch == "+":
            pending = True
            continue
        out.append(ch)
        if pending and ch in VOWELS:
            out.append(COMBINING_ACUTE)
            pending = False
    return "".join(out)


def transliterate(text: str) -> str:
    """Readable Latin transliteration with the stressed vowel accented."""
    words = re.split(r"(\s+)", text)
    return "".join(_translit_word(w) for w in words)


def _translit_word(word: str) -> str:
    has_mark = "+" in word
    out = []
    pending = False
    prev = ""
    for ch in word:
        if ch == "+":
            pending = True
            continue
        low = ch.lower()
        if low not in _TRANSLIT:
            out.append(ch)
            prev = ch
            continue
        latin = _TRANSLIT[low]
        # е at the start of a word or after a vowel/sign sounds like "ye"
        if low == "е" and (not prev or prev.lower() in VOWELS or prev.lower() in "ъь" or not prev.isalpha()):
            latin = "ye"
        stressed = (pending and ch in VOWELS) or (low == "ё" and not has_mark)
        if stressed and latin:
            v = latin[-1]
            latin = latin[:-1] + _ACUTE.get(v, v)
        if pending and ch in VOWELS:
            pending = False
        if ch.isupper() and latin:
            latin = latin[0].upper() + latin[1:]
        out.append(latin)
        prev = ch
    return "".join(out)


def normalize_words(text: str) -> list[str]:
    """Lowercase, drop stress marks and punctuation, treat ё as е, split hyphenated words."""
    text = strip_stress(text).lower().replace("ё", "е")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[-‐–—]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()
