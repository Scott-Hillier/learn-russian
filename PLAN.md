# Learn Russian: Local Speaking Practice Platform (Plan)

## Goal
A local web app that stands in for a speaking partner. It says Russian aloud, listens to you
say it back, tells you which sounds were wrong, and can hold a simple spoken conversation.
Everything runs on this Mac (M1, 8 GB RAM). A cloud LLM is an optional extra.

## The core loop
```
 ┌─ 1. HEAR ──────┐   ┌─ 2. SPEAK ─────┐   ┌─ 3. ANALYSE ───────────────┐   ┌─ 4. FEEDBACK ────────┐
 │ Native-quality │ → │ Record in the  │ → │ a) What words did you say? │ → │ Word + sound level   │
 │ TTS, normal &  │   │ browser mic    │   │ b) What sounds did you     │   │ highlights, tips,    │
 │ slow speed     │   │                │   │    actually make?          │   │ replay yours vs.     │
 └────────────────┘   └────────────────┘   │ c) Compare to target       │   │ native, retry        │
                                           └────────────────────────────┘   └──────────────────────┘
```

## Architecture
| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript, runs in the browser at `localhost` | Mic recording (MediaRecorder), waveform and pitch display, good UI for flashcards |
| Backend | Python 3.11+ with FastAPI | All the speech models live in Python |
| Storage | SQLite (via SQLModel) | Cards, review history, per-sound error stats |
| Text-to-speech | **Silero TTS (ru)**, falling back to **Piper** or macOS `say` (Milena/Yuri voices) | Natural Russian voices that run on CPU; Silero accepts stress marks (`+`) so words are stressed correctly |
| Speech-to-text | **mlx-whisper** (`small`/`medium`, Metal-accelerated) | Accurate Russian transcription on Apple Silicon |
| Pronunciation analysis | **wav2vec2 phoneme model** (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`) + **espeak-ng** for expected pronunciation | See below |
| Conversation LLM | **Ollama** with a small local model (Qwen2.5-3B / Gemma-3-4B), fully offline | 8 GB RAM limits local models to about 3–4B parameters |
| Launch | One `./start.sh` that starts backend and frontend and opens the browser | Simple local use |

### Why Whisper alone isn't enough for pronunciation
Whisper is built to guess the *intended* words. If you say "мишка" when you meant
"мышка", it will often write "мышка" anyway and hide the mistake. So pronunciation checking
uses two signals:
1. **Whisper** checks word level: did you say the right words in the right order?
2. **A phoneme recognizer** transcribes the *sounds* you actually made (IPA, no language-model
   correction). **espeak-ng** turns the target text into its expected IPA, including Russian
   vowel reduction (молоко → [məlɐˈko]) and soft/hard consonants. A Needleman–Wunsch
   alignment of the two sequences shows each sound as correct, substituted, missing or
   extra.

Errors are mapped to tips aimed at English speakers, for example:
- ы vs и
- palatalised consonants (мат / мать)
- unreduced unstressed о
- rolled р
- щ vs ш
- final devoicing (хлеб → [xlʲep])

### Implementation note (Phase 2): what changed from the original design
- **Phoneme model dropped.** Tested on native Russian, the multilingual phoneme recognizer
  (`wav2vec2-xlsr-53-espeak-cv-ft`) missed most palatalisation and heard "мать" as "b a t".
  It was too noisy to score learners fairly.
- **Replaced with a Russian letter-level CTC model** (`bond005/wav2vec2-large-ru-golos`).
  The target spelling is force-aligned to the audio, and each letter gets a
  goodness-of-pronunciation score plus a "sounded like" letter.
- **espeak-ng not needed.** Russian pronunciation rules are applied as accepted variants
  instead: vowel reduction, devoicing, silent letters and exceptions.
- **Benefit:** errors are shown on the actual letters, which suits a beginner better than IPA.
- **Calibration:** native 99.8%, 9/10 deliberate mistakes caught, English-accent voice 78%
  (see README).
- **Limitation:** vowel *quality* in unstressed syllables and word stress aren't judged,
  because the model maps sounds to spelling. Stress is left for the prosody phase.

### Implementation note (Phase 3): Letters & Sounds
- **Six lessons** covering all 33 letters:
  1. familiar letters
  2. false friends
  3. new shapes with familiar sounds
  4. soft vowels
  5. tricky sounds
  6. the two signs
- **Four steps per lesson:** Learn (letter cards), Say the letters (drill words), Read words
  (transliteration hidden until attempted), Quiz (the letter's sound, with English
  lookalikes as distractors).
- **Syllables are listen-only.** Calibration showed the pronunciation model is unreliable on
  isolated syllables ("ма", "у"), even from native voices. Drill words from each letter's
  examples and the lesson words average 98.5% with native voices.
- **Progress** is saved in SQLite (`backend/userdata/progress.db`, git-ignored). Every scored
  attempt stores per-letter scores, including attempts from the Phrases screen. A letter is
  "mastered" once it has at least 3 occurrences averaging 80% or more over its last 8. This
  per-letter data will feed minimal pairs and the problem-sounds dashboard later.
- **Content is checked by tests:** lesson words only use letters taught so far, and every
  multi-vowel word has a stress mark.

### Implementation note (Phase 4): Flashcards
- **Built-in decks:**
  - **Starter words:** 291 high-frequency words in 12 themed units, all stress-marked.
  - **Phrases:** the 32 survival phrases.
  - Built-in cards are synced on startup without overwriting your edits. They can be
    suspended but not deleted.
- **Custom decks** support add, edit, suspend and delete, plus CSV/TSV import
  (`russian,english[,notes]`). Words with more than one vowel and no stress mark are
  flagged.
- **Scheduling** uses FSRS via `py-fsrs`: default parameters, 90% desired retention, a
  study day that starts at 4am, a new-card limit per day (default 10), and a 20-minute
  learn-ahead window for learning cards.
- **Study order:** due learning cards, then due reviews, then new cards, then learning cards
  due soon.
- **Speaking recall:** a review shows the English; you say the Russian from memory, and the
  pronunciation score suggests a rating (≥85 Good, ≥55 Hard, otherwise Again). You can
  override it. A new card shows everything first, so you can listen and repeat.
- **Letter statistics:** flashcard attempts feed the per-letter scores too.
- **Not yet:** example sentences are not in the starter deck. They come with the sentence
  trainer in Phase 5.

### Implementation note (Phase 5): Sentences & sound pairs
- **Sentence trainer:** 36 beginner sentences in 6 themes, each with a word-by-word
  translation and chunk boundaries. Five steps:
  1. Listen (click any word to hear it)
  2. Words
  3. Chunks
  4. Full sentence
  5. Shadow
- **Word step skips very short words** (я, в, у). Earlier calibration showed isolated tiny
  words score unreliably, so they're practised inside chunks instead.
- **Pace feedback:** the full-sentence and shadowing steps compare your speaking length with
  the native voice (`timing` on `/api/attempt`, measured from the first to last voiced frame).
- **Shadowing:** after a countdown, the native audio plays while recording; recording stops
  0.9 s after the audio ends. Headphones are needed, or the mic picks up the native voice.
- **Sentence calibration** with native voices: full sentences 99.9%, chunks 99.7%,
  words 98.8%.
- **Sound pairs:** 9 contrast groups (ы/и, ь, х/к, р/л, ж/ш, б/п, д/т, г/к, з/с), each with
  a listening quiz and a speaking drill. Groups are ordered by your weakest per-letter scores
  (below 85%), then by importance for English speakers.
- **Pair calibration** (native audio of one word scored against the other, three voices):
  112 of 120 checks pass. The scorer can't hear the missing ь in брат/брать or полка/полька,
  so those pairs are listening-only. мат/мать and угол/уголь do work.
- **API smoke tests** (FastAPI TestClient, without loading models) now cover every route.
  They were added after a decorator mix-up briefly broke `/api/attempt`.

### Stress and intonation (later phase)
Word stress is the hardest thing to score automatically. Planned approach:
1. Force-align your audio to the target phonemes.
2. Measure each vowel's duration, loudness and pitch (via `parselmouth`/Praat).
3. Flag when the loudest or longest vowel isn't the stressed one.
4. Show your pitch contour over the native TTS contour for sentence intonation, e.g. the
   rising pitch on yes/no questions.

## Features / Modes
1. **Word drill (flashcards + speaking).** Card shows the word with its stress mark and
   meaning. You tap to hear it, record yourself, and get a score. Spaced repetition
   (**FSRS** algorithm) sets the next review from both recall and pronunciation score.
2. **Sentence trainer.** Learn a new sentence in steps:
   - listen at normal and slow speed
   - repeat it word by word
   - repeat it in chunks
   - say the full sentence
   - shadow the native audio
3. **Minimal pairs.** Short focused drills on the sounds you get wrong most (built from your
   error stats), e.g. был/бил, брат/брать.
4. **Conversation partner.** Push-to-talk voice chat. The LLM plays a scenario (café, directions, small talk) using
   vocabulary for your level. Each reply comes with an optional correction panel covering
   grammar and pronunciation flags, and useful new words can be added to your deck with
   one click.
5. **Progress dashboard.** Cards due, streak, accuracy over time, and your "problem sounds"
   heatmap.
6. **Content.**
   - Seed deck of about 500 high-frequency words with stress marks and example sentences
   - Import from Anki `.apkg` / CSV
   - Add your own words (stress marks filled in automatically, e.g. with `russtress`, and
     editable)

## Project layout
```
learn-russian/
├── start.sh
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app & routes
│   │   ├── speech/tts.py        # Silero/Piper/say wrapper + audio cache
│   │   ├── speech/asr.py        # mlx-whisper transcription
│   │   ├── speech/phonemes.py   # wav2vec2 phoneme recognition + espeak G2P
│   │   ├── speech/scoring.py    # alignment, scores, error → tip mapping
│   │   ├── speech/prosody.py    # stress/pitch analysis (later phase)
│   │   ├── srs/fsrs.py          # spaced repetition scheduling
│   │   ├── chat/llm.py          # Claude API / Ollama adapter
│   │   └── db/models.py         # SQLModel tables
│   ├── data/seed_deck.csv
│   └── tests/
└── frontend/
    └── src/
        ├── pages/  (Drill, Sentence, MinimalPairs, Conversation, Dashboard, Deck)
        └── components/ (Recorder, Waveform, PitchChart, PhonemeDiff, CardView)
```

## Build phases
Each phase ends with something usable.

**Phase 1: Hear and say (foundation)**
- Backend and frontend skeleton, `start.sh`
- TTS endpoint with caching; browser recorder component
- Whisper transcription and a word-level diff
- Result: type or pick a word or sentence, hear it, say it, see which words were recognised

**Phase 2: Pronunciation scoring**
- espeak-ng G2P, wav2vec2 phoneme recognition, alignment
- Per-sound colour-coded feedback, overall score and English-speaker tips
- Side-by-side playback of your recording and the native audio
- Test set: record known good and bad pronunciations to tune thresholds

**Phase 3: Flashcards and SRS**
- SQLite models, FSRS scheduling, seed deck, Anki/CSV import, deck editor
- Word drill mode ties SRS and pronunciation scoring together

**Phase 4: Sentence trainer and minimal pairs**
- Chunked learning flow, slow playback, shadowing
- Minimal-pair drills generated from per-sound error stats

**Phase 5: Conversation partner**
- LLM adapter (Claude API or Ollama), scenario prompts, level control
- Voice loop: record → Whisper → LLM → TTS, plus the correction panel and "add to deck"

**Phase 6: Stress, intonation and progress**
- Prosody analysis and pitch-contour overlay
- Progress dashboard

## Constraints and honest caveats
- **8 GB RAM.** Models are loaded lazily and unloaded when idle. Whisper `small` is the
  default (`medium` is optional). A local LLM and Whisper together will be tight, which is
  why Claude API is the recommended conversation backend.
- **Automated scoring is less precise than a human tutor.** It reliably catches missing or
  wrong sounds, ы/и confusion and hard/soft consonant errors. It is less reliable on subtle
  vowel quality and on stress. Feedback will be framed as guidance rather than a verdict.
- **TTS stress.** Silero stresses correctly when given stress marks. The seed deck includes
  them, so native audio is correct.
- **First run** downloads roughly 1.5–2 GB of models, then everything works offline
  (except the Claude API, if chosen).

## Decisions (2026-09-14)
1. **Fully offline.** The conversation partner uses Ollama with a small local model
   (Qwen2.5-3B or Gemma-3-4B). Scenarios stay tightly scoped and beginner-level so a small
   model can cope. Nothing reaches the internet after the first model download.
2. **Complete beginner.** Changes to the plan:
   - Every Russian word shows **transliteration + English** (toggleable later).
   - A new **Alphabet & Sounds** module comes before flashcards: all 33 letters, each with
     native audio, a speak-and-check drill and example words.
   - The starter deck is graded: greetings and survival phrases, then the top 500 words.
   - Conversation scenarios are unlocked only after enough vocabulary is learned.
3. **No Anki import.** Moved to "nice to have". CSV import and a manual deck editor stay.

Revised order:
1. Hear and say ✅ (done 2026-09-14)
2. Pronunciation scoring ✅ (done 2026-09-14; see the implementation note below)
3. Alphabet & Sounds ✅ (done 2026-09-14; see the implementation note below)
4. Flashcards and SRS ✅ (done 2026-09-14; see the implementation note below)
5. Sentence trainer and minimal pairs ✅ (done 2026-09-14; see the implementation note below)
6. Conversation partner (Ollama)
7. Stress, intonation and progress
