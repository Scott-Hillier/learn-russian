from app.speech.compare import build_feedback, recognise_words
from app.text import display_stress, normalize_words, target_words, transliterate


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
