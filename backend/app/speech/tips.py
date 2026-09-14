"""Pronunciation advice for sounds English speakers commonly get wrong."""

# (target letter, letter it sounded like) → advice. heard=None is the fallback for that letter.
SOUND_TIPS: dict[tuple[str, str | None], str] = {
    ("ы", None): "ы has no English equivalent. Say “ee”, then pull your tongue back without moving your lips.",
    ("и", "ы"): "и is a clear “ee”: keep your tongue forward and lips spread.",
    ("ь", None): "ь softens the consonant before it. Finish with the middle of your tongue raised, as if starting a tiny “y”.",
    ("щ", None): "щ is a long, soft “shsh”, with the tongue higher and further forward than for ш.",
    ("ш", "щ"): "ш is a hard “sh”: pull your tongue back and don't let it go soft.",
    ("ш", None): "ш is a hard “sh” with the tongue pulled back.",
    ("ж", None): "ж is like the “s” in “pleasure”, but harder, with the tongue pulled back.",
    ("х", None): "х is a raspy “kh” from the back of the mouth, like Scottish “loch”. It isn't “h” or “k”.",
    ("р", None): "р is tapped or rolled: flick the tip of your tongue against the ridge behind your top teeth.",
    ("л", None): "л is a “dark” l, as in “full”: keep the back of your tongue low.",
    ("ц", None): "ц is “ts” as in “cats”, said as one quick sound.",
    ("ч", None): "ч is a soft “ch” as in “cheese”.",
    ("й", None): "й is a short “y” glide, as in “boy”.",
    ("у", None): "у is a rounded “oo” as in “food”. Push your lips forward.",
    ("ю", None): "ю is “yu” as in “you”.",
    ("я", None): "я is “ya” as in “yard”.",
    ("е", None): "е is “ye” (or “e” after a consonant) as in “yet”.",
    ("э", None): "э is an open “e” as in “bet”.",
}
FULL_VOWEL_TIPS = {"у", "ю", "я", "е", "э", "о", "а"}
UNSTRESSED_VOWEL = ("Unstressed vowels are short and weak in Russian. Say the stressed syllable strongly, "
                    "keep this one brief, and copy the slow audio.")
STRESSED_O ="A stressed о is a full, round “o” as in “more”. Round your lips."
STRESSED_A = "A stressed а is an open “ah” as in “father”."


def letter_tip(word: str, letter: dict) -> tuple[str, bool]:
    """Return (tip text, whether it contains sound-specific advice)."""
    char = letter["char"].lower()
    heard = letter.get("heard_as")
    lead = f"In “{word}”, “{char}” sounded like “{heard}”." if heard else f"In “{word}”, “{char}” wasn't clear."
    advice = SOUND_TIPS.get((char, heard))
    if not advice and char in FULL_VOWEL_TIPS and not letter["stressed"]:
        advice = UNSTRESSED_VOWEL  # "ye as in yet" style advice only fits stressed vowels
    advice = advice or SOUND_TIPS.get((char, None))
    if not advice and letter["stressed"]:
        advice = {"о": STRESSED_O, "а": STRESSED_A}.get(char)
    return f"{lead} {advice or 'Play the word slowly and copy that sound.'}", advice is not None
