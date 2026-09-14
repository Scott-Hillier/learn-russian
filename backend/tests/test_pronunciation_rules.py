import numpy as np

from app.speech.pronunciation import analyse_word, ctc_align


def test_stress_and_vowel_reduction():
    letters = analyse_word("молок+о")
    assert [l.stressed for l in letters] == [False, False, False, False, False, True]
    assert "а" in letters[1].alts and "а" in letters[3].alts
    assert "а" not in letters[5].alts  # stressed о must be a real о


def test_single_vowel_words_are_stressed_except_clitics():
    assert analyse_word("дом")[1].stressed
    assert not analyse_word("не")[1].stressed


def test_yo_is_always_stressed():
    letters = analyse_word("ещё")
    assert letters[2].stressed and letters[2].norm == "е"


def test_final_devoicing_and_assimilation():
    assert "п" in analyse_word("хлеб")[3].alts
    assert "ф" in analyse_word("вторник")[0].alts   # в before voiceless т
    assert "г" in analyse_word("вокзал")[2].alts    # к before voiced з
    assert "к" in analyse_word("друг")[3].alts


def test_silent_letters():
    letters = analyse_word("здр+авствуйте")
    assert [l.char for l in letters if l.silent] == ["в"]
    assert letters[4].silent and not letters[7].silent
    assert analyse_word("+Анна")[2].silent  # doubled consonant


def test_exceptions():
    assert "ш" in analyse_word("что")[0].alts
    assert "в" in analyse_word("сег+одня")[2].alts


def test_ctc_align_simple():
    # vocab: 0 blank, 1 'a', 2 'b'. Frames: a a blank b
    probs = np.array([[0.1, 0.8, 0.1], [0.1, 0.8, 0.1], [0.8, 0.1, 0.1], [0.1, 0.1, 0.8]])
    frames = ctc_align(np.log(probs), [1, 2])
    assert frames == [[0, 1], [3]]


def test_ctc_align_repeated_tokens_need_blank():
    probs = np.array([[0.1, 0.9], [0.9, 0.1], [0.1, 0.9]])
    assert ctc_align(np.log(probs), [1, 1]) == [[0], [2]]
    assert ctc_align(np.log(probs[:1]), [1, 1]) is None
