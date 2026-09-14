# Говори́! Learn Russian by speaking

A local, offline speaking partner. Hear a phrase, say it back, and get letter-by-letter
pronunciation feedback. See [PLAN.md](PLAN.md) for the roadmap.

## Run
```bash
./start.sh
```
Your browser opens at http://localhost:8000. The first run installs packages and downloads
the speech models (about 3 GB). After that the app works fully offline.

Requirements: macOS on Apple Silicon, Python 3.10+, Node 18+, `ffmpeg` (`brew install ffmpeg`).

## Letters & Sounds (start here if you're new)
The **🔤 Letters & Sounds** screen teaches all 33 Cyrillic letters in 6 lessons. Each lesson
has four steps:
1. **Learn** each letter: its sound, English lookalike warnings and example words, all with audio.
2. **Say the letters** in real words, with a score for that letter.
3. **Read words** without transliteration, then say them.
4. **Quiz** on letter sounds.

Letters turn amber once practised and green once you say them well consistently. Progress is
saved locally in `backend/userdata/progress.db`.

## Flashcards
The **🃏 Flashcards** screen uses spaced repetition (FSRS) to review vocabulary *out loud*:
- **Reviews:** you see the English and say the Russian from memory (`Space`), or press
  `Enter` to reveal it. Your pronunciation score suggests a rating; press `1`–`4`
  (Again / Hard / Good / Easy) to accept or override it.
- **New cards** show the Russian, transliteration and audio first so you can repeat them.
- **Decks:** *Starter words* (291 words in 12 units) and *Phrases* are built in. You can
  create your own decks, add cards, or import a CSV (`russian,english[,notes]`, with `+`
  before the stressed vowel).
- **Settings:** set how many new cards to introduce per day in the sidebar.

## How to practise phrases
1. Pick a phrase in the sidebar, or type your own. Mark stress with `+`, e.g. `молок+о`.
2. **🔊 Listen** (`L`) or **🐢 Slow** (`S`).
3. **🎙 Say it** (`Space`). Recording stops when you pause.
4. Each letter turns green (clear), amber (almost) or red (needs work). Faded letters are
   silent. Click a word to see what each problem sound was heard as, and to hear that word
   on its own. Compare **My recording** with **Native**.

## How pronunciation scoring works
- **Whisper** transcribes what you said. It is shown as "I heard", but it auto-corrects, so it
  isn't used for scoring.
- **Letter scoring:** a Russian letter-level speech model (`bond005/wav2vec2-large-ru-golos`,
  with no language model to auto-correct you) is force-aligned to the target spelling. Each
  letter is scored by how strongly the model heard that letter at that point, and the
  strongest competing letter becomes "sounded like …".
- **Natural pronunciation is accepted.** Rules in
  [pronunciation.py](backend/app/speech/pronunciation.py) allow unstressed vowel reduction
  (молоко ≈ "малако"), final devoicing (хлеб ≈ "хлеп"), silent letters (здравствуйте) and
  common exceptions (что ≈ "што").

Calibration against synthetic speech (`cd backend && .venv/bin/python -m scripts.calibrate`):

| Test | Result |
|---|---|
| Native voices (160 recordings) | 99.8% average, 159/160 ≥ 85% |
| Deliberate mistakes (ы→и, щ→ш, х→к, р→л …) | 9/10 caught |
| English-accent voice | 78% average, with specific sounds flagged |

Known weak spots:
- A missing soft sign at the end of a word (спать → "спат") is often not detected.
- Word stress isn't checked yet (Phase 7).

## Configuration (environment variables)
| Variable | Default | Notes |
|---|---|---|
| `WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | `mlx-community/whisper-small-mlx` uses less RAM |
| `PRONUNCIATION_MODEL` | `bond005/wav2vec2-large-ru-golos` | Any Russian character-level wav2vec2 CTC model |
| `TTS_SPEAKER` | `xenia` | Silero voices: `aidar`, `baya`, `kseniya`, `xenia`, `eugene` |
| `PORT` | `8000` | |

## Development
```bash
cd backend && .venv/bin/python -m pytest -q          # tests
cd backend && .venv/bin/uvicorn app.main:app --reload  # API on :8000
cd frontend && npm run dev                            # UI on :5173 with hot reload
```

The Silero TTS model is licensed CC BY-NC 4.0 (fine for personal use).
