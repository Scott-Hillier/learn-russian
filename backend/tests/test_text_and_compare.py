from app.speech.compare import compare
from app.text import display_stress, normalize_words, transliterate


def test_display_stress():
    assert display_stress("прив+ет") == "приве́т"


def test_transliterate():
    assert transliterate("Прив+ет") == "Privét"
    assert transliterate("Здр+авствуйте") == "Zdrávstvuyte"
    assert transliterate("Ещё раз") == "Yeshchyó raz"
    assert transliterate("Мен+я зов+ут") == "Menyá zovút"


def test_normalize():
    assert normalize_words("Вы говор+ите по-англ+ийски?") == ["вы", "говорите", "по", "английски"]
    assert normalize_words("Ещё!") == ["еще"]


def test_compare_perfect():
    r = compare("Я не поним+аю", "Я не понимаю.")
    assert r["score"] == 100
    assert [w["status"] for w in r["words"]] == ["correct"] * 3


def test_compare_missing_and_close():
    r = compare("Я не поним+аю", "Я понимаю")
    assert [w["status"] for w in r["words"]] == ["correct", "missing", "correct"]
    r = compare("Спас+ибо", "Спасиба")
    assert r["words"][0]["status"] == "close"


def test_compare_nothing_heard():
    r = compare("Прив+ет", "")
    assert r["score"] == 0 and r["words"][0]["status"] == "missing"
