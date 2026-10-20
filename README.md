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

## 🏠 Today (start here)
The app opens on **Today**. It shows your next step (a lesson, a test or a fix-up lesson); press `Enter` to
start it. Below that are your path through the course, how often you're right first time on each kind of
exercise, the things you've missed lately, and your test results. Already know some Russian? Take the
**placement test** shown there to start further on.

## 📘 Lessons
**Lessons** is a 60-lesson Direct Instruction course (see [PLAN.md](PLAN.md)), from «Это кошка» to the past
and future tense, shopping, cafés and asking the way. Do one lesson at a time, in order:
- **Mixed exercises:** each lesson has short exercises from different tracks: new words, sentence patterns,
  listening, numbers and a mini dialogue. Every lesson also reviews earlier ones.
- **How new items are taught:** you hear it, say it after the voice, then say it on your own from a picture.
  It comes back again a few items later.
- **When you get one wrong:** you hear the right answer and say it after the voice. The two items before it
  are asked again, and the missed one comes back a few items later.
- **Passing:** an exercise passes at **90% right first time**. Below that you can **go again** (the same
  exercise in a new order; `Space`) or move on (`Enter`): whatever you missed comes back in review. After a
  passed exercise, `Space` or `Enter` moves on. The next lesson unlocks once you've finished every exercise.
- **Choose the right word:** some exercises show a sentence with a gap ("___ сок") and you pick the form
  (мой / моя / моё). These cover differences that speech checking can't hear reliably.
- **Hands-free** (on by default): the mic opens by itself after each question and stops when you pause.
  `Space` answers or stops, `R` repeats the question, `1`–`4` pick an answer in listening exercises, and `Esc`
  pauses hands-free.
- **Answer checking:** your answer is compared with the expected answer and the likely wrong ones (кошка vs
  кошку, тут vs там). Common English-speaker sounds (ы said as и, a hard consonant instead of a soft one)
  still count as the right answer; the coloured letters show them so you can work on them. If it isn't
  clear what you said, you're asked to say it again. If the checker gets it wrong, **✓ I said it right**
  (`O`) counts it as right; that is saved separately.
- **Review:** each lesson starts with review. Things you've missed lately come first, then lesson words that
  are due in your flashcards (answering them there counts as their flashcard review), then older items.
- **Tests:** every 5 lessons there's a short test: one try at each item, no help. Taking it unlocks the next
  five lessons; 90% passes it. Below that, an optional fix-up lesson goes over what you missed, and then you
  can retake the test. You can also take a unit's test early to skip lessons you already know.
- **Flashcards:** words a lesson teaches are linked to it ("📘 Lesson 3") and join your flashcard schedule
  when you pass the lesson.

Everything else (letters, flashcards, sentences, sound pairs, conversation, phrases) is under **Practice** in
the sidebar, for reviewing any content whenever you like. In **🤖 Conversation**, the level "Only words from
my lessons" keeps the partner to the words and grammar you've been taught; any other word it uses is
underlined.

## Letters & Sounds
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
  `Enter` to reveal it. Your pronunciation score suggests a rating: `Enter` accepts it (or
  picks Good if you didn't speak), and `1`–`4` (Again / Hard / Good / Easy) override it.
- **Groups:** new words come in groups (10 by default). *Learn group N* introduces the next
  group's words; finish it and *Next group →* starts the next one straight away. There's no
  daily limit. Leave part-way through and the group picks up where you left off.
- **New cards** show the Russian, its meaning and audio first so you can repeat them.
- **⭐ Learned words:** every word you've learned from any deck, so after three groups of 10 it
  has 30 words. *Review all* goes through them shuffled, as often as you like: `1` sends a card
  to the end of the review, `Enter` moves on. Scores count towards your progress, but these
  reviews never change the spaced-repetition schedule.
- **Decks:** *Starter words* (291 words in 12 units) and *Phrases* are built in. You can
  create your own decks, add cards, or import a CSV (`russian,english[,notes]`, with `+`
  before the stressed vowel).
- **Review all N →** on a deck page goes through that deck's cards, shuffled, the same way as the
  ⭐ deck: it includes cards you've never studied and never changes the spaced-repetition
  schedule. *Learn group N* is still there when you want the scheduled run through the deck.
- **Building a deck from words you already have:** every card table (⭐ Learned words and each
  deck) has tick boxes and an *Add to* bar. Pick an existing deck or *＋ New deck…*, tick the
  words and add them, or use *＋ Add* on a single row. The copies start as new cards in the
  target deck, so they're learned on their own schedule; the originals are untouched and words
  the deck already has are skipped. On ⭐ Learned words, sort by *Forgotten most* to put the
  words you keep lapsing on at the top.
- **Settings:** set how many words are in a group (1–100) in the sidebar.

## Sentences
The **🗣 Sentences** screen teaches 36 everyday sentences in five steps:
1. **Listen**, with a word-by-word translation.
2. **Say the words.**
3. **Say the chunks.**
4. **Say the full sentence.** You also get feedback on your pace compared with the native
   voice.
5. **Shadow:** speak along with the native audio. Use headphones, otherwise the mic hears
   the native voice.

## Sound pairs
The **👂 Sound pairs** screen drills pairs of words that differ by one sound (был/бил,
мат/мать, дом/том…):
- **Listen & choose** trains your ear.
- **Say the pairs** checks you produce the difference.
- **Ordering:** groups for the sounds you score lowest on elsewhere in the app are listed
  first.

## Conversation partner
The **🤖 Conversation** screen is a role-play partner that runs locally with
[Ollama](https://ollama.com) and `gemma3:4b`. Scenarios: café, meeting someone, asking
directions, market, hotel, free chat.
- **Talking:** speak (`Space`) or type in Russian. The partner replies in simple Russian
  with an English translation and audio.
- **Corrections:** your sentences are checked, and corrections show the changed words
  highlighted. They are AI suggestions and can occasionally be wrong.
- **Suggested replies:** pick one, practise saying it with pronunciation scoring, then send it.
- **Numbers:** digits are always written out as Russian words ("двести пятьдесят рублей", not
  "250 рублей"), so you can hear, read and practise them. Ordinals like "5-й" are left as typed.
- **Saving:** ⭐ saves a phrase to the *Conversation phrases* flashcard deck.

Setup: `brew install ollama`. `./start.sh` then starts Ollama and downloads the model
(about 3 GB) on first run. Replies take about 7 seconds on an 8 GB M1. Use
`CHAT_MODEL=...` to try another Ollama model.

## Progress & intonation
- **📈 Progress** shows your streak, daily practice, pronunciation score over time, a
  heatmap of how clearly you say each letter, and the sounds to work on next.
- **Intonation chart:** after saying a phrase or a full sentence you see your pitch contour
  over the native voice's, with stressed syllables marked. Match the rises and falls, e.g.
  the rise at the end of "Как дела?".
- **Word stress** isn't graded automatically. It was tested and found unreliable (see
  [PLAN.md](PLAN.md)), so use the stress marks, the slow audio and the
  intonation chart.

## How to practise phrases
1. Pick a phrase in the sidebar, or type your own. Mark stress with `+`, e.g. `молок+о`.
2. **🔊 Listen** (`L`) or **🐢 Slow** (`S`).
3. **🎙 Say it** (`Space`). Recording stops when you pause.
4. Each letter turns green (clear), amber (almost) or red (needs work). Faded letters are
   silent. Click a word to see what each problem sound was heard as, and to hear that word
   on its own. Compare **▶ You** (`P`) with **🔊 Listen**.
5. **Next** (`Enter`) moves on, and the next item plays automatically (turn this off with
   *Auto-play* under the buttons).

## Keyboard shortcuts
Every practice screen keeps its buttons in a bar pinned to the bottom of the window, so they stay
in the same place from one item to the next. The keys it uses are listed under the buttons:

| Key | Action |
|---|---|
| `Space` | Record / stop (Shadow: start) |
| `Enter` | Next item or step (quizzes: next question; flashcards: reveal, then accept the rating) |
| `←` `→` | Previous / next item or letter |
| `L` / `S` | Listen / listen slowly |
| `P` | Play your recording |
| `1`–`4` | Quiz answer, or flashcard rating |
| `R` | Sound pairs: replay the word; finished quiz: try again |

Shortcuts use the physical key, so they still work with a Russian keyboard layout. They're off
while you type in a text box.

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
- Word stress isn't graded automatically (tested and found unreliable; see the Progress & intonation section).
- Each letter is judged on the short moment where the model heard it, so scores are close to all-or-nothing.
  When the model heard no clear letter there, feedback says the sound "wasn't clear" instead of guessing
  what it sounded like.
- "д sounded like т" (and б→п, г→к) at the start of a word is usually real: English b/d/g are barely voiced
  there, and Russian hears them as п/т/к. The tip explains how to voice them.
- Short clicks before or after speech (e.g. pressing `Space` to start or stop) are trimmed off before scoring.

To check how scoring treats your own voice, start the app with `SAVE_RECORDINGS=1 ./start.sh`. Your last 60
attempts (audio and feedback) are then kept in `backend/userdata/recordings/` (not committed).

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
