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


def target_words(text: str) -> list[str]:
    """Split text into words, keeping '+' stress marks and letters only (hyphenated words split)."""
    words = []
    for raw in re.split(r"[\s\-‐–—]+", text):
        word = "".join(ch for ch in raw if ch.isalpha() or ch == "+")
        if strip_stress(word):
            words.append(word)
    return words


MAX_SPELLED_NUMBER = 999_999_999

# Stress is marked as everywhere else in the app, and left off one-syllable words by convention.
_ONES ={0: "ноль", 1: "од+ин", 2: "два", 3: "три", 4: "чет+ыре", 5: "пять",
         6: "шесть", 7: "семь", 8: "в+осемь", 9: "д+евять"}
_ONES_BY_GENDER = {"f": {1: "одн+а", 2: "две"}, "fa": {1: "одн+у", 2: "две"}, "n": {1: "одн+о"}}
_TEENS = ["д+есять", "од+иннадцать", "двен+адцать", "трин+адцать", "четыр+надцать", "пятн+адцать",
          "шестн+адцать", "семн+адцать", "восемн+адцать", "девятн+адцать"]
_TENS = {2: "дв+адцать", 3: "тр+идцать", 4: "с+орок", 5: "пятьдес+ят", 6: "шестьдес+ят",
         7: "с+емьдесят", 8: "в+осемьдесят", 9: "девян+осто"}
_HUNDREDS = {1: "сто", 2: "дв+ести", 3: "тр+иста", 4: "чет+ыреста", 5: "пятьс+от",
             6: "шестьс+от", 7: "семьс+от", 8: "восемьс+от", 9: "девятьс+от"}
_THOUSAND = ("т+ысяча", "т+ысячи", "т+ысяч")
_MILLION = ("милли+он", "милли+она", "милли+онов")

# Symbols the conversation partner tends to write instead of the word: (one, few, many) forms.
_UNITS = {"%": ("проц+ент", "проц+ента", "проц+ентов"),
          "₽": ("рубль", "рубл+я", "рубл+ей"),
          "$": ("д+оллар", "д+оллара", "д+олларов"),
          "€": ("+евро", "+евро", "+евро")}

# A thousands-separated group ("1 000"), then a decimal ("2,5"), then a plain run of digits — each
# optionally followed by a unit symbol, which is swallowed into the match and spelled out with it.
_NUMBER = re.compile(r"(\d{1,3}(?:[\s  ]\d{3})+|\d+[.,]\d+|\d+)(?:\s*([%₽$€]))?")
_ORDINAL_SUFFIX = re.compile(r"-[а-яё]", re.IGNORECASE)


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    """Pick the form a Russian noun takes after `n`: 1 рубль, 2 рубля, 5 рублей."""
    if n % 100 // 10 == 1:
        return forms[2]
    last = n % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def _under_thousand(n: int, gender: str) -> list[str]:
    words = []
    if n >= 100:
        words.append(_HUNDREDS[n // 100])
        n %= 100
    if 10 <= n <= 19:
        words.append(_TEENS[n - 10])
        return words
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
    if n:
        words.append(_ONES_BY_GENDER.get(gender, {}).get(n) or _ONES[n])
    return words


def spell_number(n: int, gender: str = "m") -> str:
    """A whole number as stressed Russian words, e.g. 250 -> "дв+ести пятьдес+ят"."""
    if n == 0:
        return _ONES[0]
    words: list[str] = []
    millions, rest = divmod(n, 1_000_000)
    if millions:
        words += _under_thousand(millions, "m") + [_plural(millions, _MILLION)]
    thousands, rest = divmod(rest, 1000)
    if thousands:
        # "тысяча рублей", not "одна тысяча рублей" — the bare form is what people say.
        words += ([] if thousands == 1 else _under_thousand(thousands, "f")) + [_plural(thousands, _THOUSAND)]
    if rest:
        words += _under_thousand(rest, gender)
    return " ".join(words)


def _gender_after(n: int, following: str) -> str:
    """Guess the form a numeral must agree with from the noun after it.

    Only 1 (один/одна/одно/одну) and 2 (два/две) inflect here, and in both positions the noun's
    ending gives it away. After 1 the noun is singular and carries the phrase's case: "мин+ута" ->
    одна, "мин+уту" (accusative, as in "подождите одну минуту") -> одну, "рубл+ь" -> один. After 2
    the noun is genitive singular: "мин+уты" -> две, "рубл+я" -> два.
    """
    word = strip_stress(following).lower()
    if not word or n % 10 not in (1, 2) or n % 100 // 10 == 1:
        return "m"
    if n % 10 == 1:
        if word.endswith(("а", "я")):
            return "f"
        if word.endswith(("у", "ю")):
            return "fa"
        return "n" if word.endswith(("о", "е")) else "m"
    return "f" if word.endswith(("ы", "и")) else "m"


def _match_case(spelled: str, text: str, start: int) -> str:
    """Capitalise the spelled-out number if the digits opened a sentence ("250 рублей." -> "Двести…")."""
    before = text[:start].rstrip()
    if before and before[-1] not in ".!?…":
        return spelled
    head, mark = (spelled[1:], "+") if spelled.startswith("+") else (spelled, "")
    return mark + head[:1].upper() + head[1:]


def expand_numbers(text: str) -> str:
    """Write digits out as Russian words so they can be spoken, read and scored.

    Silero's Russian voice has no number normaliser and simply drops digits, and the letter-level
    pronunciation scorer only sees letters — so "Это стоит 250 рублей" was read aloud, and
    practised, as "Это стоит рублей". Ordinals ("5-й") are left alone rather than mangled.
    """
    text = re.sub(r"(?<=\d):(?=\d)", " ", text)  # 10:30 -> "десять тридцать"

    def replace(m: re.Match) -> str:
        token, symbol, after = m.group(1), m.group(2), text[m.end():]
        if _ORDINAL_SUFFIX.match(after):  # "5-й", "20-го" — spelling these needs the case, so leave them
            return m.group()
        whole, _, fraction = token.partition(",") if "," in token else token.partition(".")
        n = int(re.sub(r"[\s  ]", "", whole))
        if n > MAX_SPELLED_NUMBER or len(fraction) > 9:
            return m.group()
        if symbol:
            return _match_case(f"{spell_number(n)} {_plural(n, _UNITS[symbol])}", text, m.start())
        if fraction:
            zeros = [_ONES[0]] * (len(fraction) - len(fraction.lstrip("0")))
            tail = [spell_number(int(fraction))] if fraction.lstrip("0") else []
            return _match_case(" ".join([spell_number(n), "запят+ая", *zeros, *tail]), text, m.start())
        following = re.match(r"[\s  ]*([а-яё]+)", after, re.IGNORECASE)
        return _match_case(spell_number(n, _gender_after(n, following.group(1) if following else "")),
                           text, m.start())

    return " ".join(_NUMBER.sub(replace, text).split())


def normalize_words(text: str) -> list[str]:
    """Lowercase, drop stress marks and punctuation, treat ё as е, split hyphenated words."""
    text = strip_stress(text).lower().replace("ё", "е")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[-‐–—]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()
