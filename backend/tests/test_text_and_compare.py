from app.speech.compare import build_feedback, recognise_words
from app.text import (display_stress, expand_numbers, normalize_words, spell_number, strip_stress,
                      target_words, transliterate)


def spelled(text: str) -> str:
    return strip_stress(expand_numbers(text))


def test_spell_number():
    assert spell_number(0) == "ноль"
    assert strip_stress(spell_number(250)) == "двести пятьдесят"
    assert strip_stress(spell_number(21)) == "двадцать один"
    assert strip_stress(spell_number(1000)) == "тысяча"  # not "одна тысяча"
    assert strip_stress(spell_number(3_000_000)) == "три миллиона"
    assert strip_stress(spell_number(999_999_999)) == (
        "девятьсот девяносто девять миллионов девятьсот девяносто девять тысяч девятьсот девяносто девять")


def test_expand_numbers_agrees_with_the_following_noun():
    # Only один/одна/одну and два/две inflect, and the noun's ending says which is needed.
    assert spelled("Дайте 2 рубля.") == "Дайте два рубля."
    assert spelled("У меня 2 минуты.") == "У меня две минуты."
    assert spelled("Мне 1 минута.") == "Мне одна минута."
    assert spelled("Подождите 1 минуту.") == "Подождите одну минуту."
    assert spelled("Это 1 слово.") == "Это одно слово."
    assert spelled("1 рубль.") == "Один рубль."  # capitalised: the number opened the sentence
    assert spelled("Мне 21 год.") == "Мне двадцать один год."


def test_expand_numbers_handles_separators_units_and_ordinals():
    assert spelled("Это стоит 1 000 рублей.") == "Это стоит тысяча рублей."
    assert spelled("Сейчас 10:30.") == "Сейчас десять тридцать."
    assert spelled("Скидка 50%.") == "Скидка пятьдесят процентов."
    assert spelled("Это стоит 250 ₽.") == "Это стоит двести пятьдесят рублей."
    assert spelled("Вес 2,5 кг.") == "Вес два запятая пять кг."
    assert spelled("Я живу на 5-м этаже.") == "Я живу на 5-м этаже."  # ordinals need the case: left alone
    assert spelled("Нет чисел здесь.") == "Нет чисел здесь."


def test_expanded_numbers_can_be_spoken_and_scored():
    """The whole point: digits used to vanish from the voice and the letter-level scorer."""
    expanded = expand_numbers("Это ст+оит 250 рублей.")
    assert target_words(expanded) == ["Это", "ст+оит", "дв+ести", "пятьдес+ят", "рублей"]
    assert display_stress(expanded) == "Это сто́ит две́сти пятьдеся́т рублей."


def test_display_stress():
    assert display_stress("прив+ет") == "приве́т"


def test_transliterate():
    assert transliterate("Прив+ет") == "Privét"
    assert transliterate("Здр+авствуйте") == "Zdrávstvuyte"
    assert transliterate("Ещё раз") == "Yeshchyó raz"
    assert transliterate("Мен+я зов+ут") == "Menyá zovút"


def test_normalize_and_target_words():
    assert normalize_words("Вы говор+ите по-англ+ийски?") == ["вы", "говорите", "по", "английски"]
    assert normalize_words("Ещё!") == ["еще"]
    assert target_words("Вы говор+ите по-англ+ийски?") == ["Вы", "говор+ите", "по", "англ+ийски"]


def test_recognise_words():
    words, extra = recognise_words("Я не поним+аю", "Я понимаю")
    assert [w["recognized"] for w in words] == ["correct", "missing", "correct"]
    words, _ = recognise_words("Спас+ибо", "Спасиба")
    assert words[0]["recognized"] == "close"
    _, extra = recognise_words("Прив+ет", "Привет привет")
    assert extra == ["привет"]


def _letters(word, statuses, heard=None):
    return [{"char": c, "stressed": False, "status": s, "heard_as": heard if s != "good" else None}
            for c, s in zip(word, statuses)]


def test_feedback_uses_pronunciation_scores():
    pron = [{"text": "М+ышка", "display": "", "score": 80,
             "letters": _letters("Мышка", ["good", "wrong", "good", "good", "good"], heard="и")}]
    r = build_feedback("М+ышка", "мишка", pron)
    assert r["score"] == 80 and r["words"][0]["status"] == "close"
    assert "ы" in r["tips"][0] and "и" in r["tips"][0]


def test_feedback_without_acoustic_model_or_audio():
    r = build_feedback("Прив+ет", "", None)
    assert r["score"] == 0 and r["words"][0]["status"] == "missing"
    r = build_feedback("Прив+ет", "привет", None)
    assert r["score"] == 100 and r["words"][0]["status"] == "good"


def test_devoiced_consonant_gets_voicing_advice():
    from app.speech.tips import letter_tip
    text, specific = letter_tip("дом", {"char": "д", "stressed": False, "heard_as": "т"})
    assert specific and "voiced" in text and "sounded like “т”" in text
    text, _ = letter_tip("дом", {"char": "д", "stressed": False, "heard_as": None})
    assert "wasn't clear" in text
