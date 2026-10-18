# Learn Russian: Plan

## Goal
A local, fully offline app that teaches Russian from zero to simple conversation. It stands in
for a teacher and a speaking partner. It runs on an M1 Mac with 8 GB of RAM, and nothing reaches
the internet after the first model download.

The method is **Direct Instruction (DI)**: one scripted lesson a day, built from short
exercises across several tracks, with mastery required before moving on. The original toolbox
screens stay as a **Practice** area, for reviewing any content at any time.

## What already exists
| Area | What it does |
|---|---|
| Speech engine | Silero TTS (stress via `+` marks, normal and slow speeds, macOS `say` fallback), mlx-whisper, letter-level pronunciation scoring, pace and intonation analysis |
| 🔤 Letters & Sounds | 33 letters in 6 lessons: learn, say, read, quiz |
| 🃏 Flashcards | FSRS spaced repetition, spoken recall, built-in and custom decks, CSV import, ⭐ learned words |
| 🗣 Sentences | 36 sentences: listen, words, chunks, full sentence, shadowing |
| 👂 Sound pairs | 9 contrast groups: listening quiz and speaking drill |
| 🤖 Conversation | `gemma3:4b` on Ollama: 6 scenarios, corrections shown as highlighted rewrites, suggested replies |
| 📈 Progress | Streak, daily activity, score trend, letter heatmap, sounds to work on |

## What the speech stack can and can't judge
These findings come from calibration in phases 1–7, and the lesson design has to respect them.

- **Letter scorer** (`bond005/wav2vec2-large-ru-golos`, force-aligned to the target spelling):
  - **Accuracy:** native voices score 99.8%. It catches 9 of 10 deliberate mistakes (ы→и, щ→ш, х→к, р→л…).
  - **Accepted variants:** reductions, devoicing and silent letters are treated as correct,
    not as errors.
- **Not judged reliably:**
  - **Isolated syllables and very short words** (я, в, у) score unreliably. Practise them
    inside phrases.
  - **A missing ь** after a hard consonant is often not heard (брат/брать, спать → "спат").
  - **Word stress:**
    - Tested on 211 words with the stress moved. At most ~42% of errors were caught when
      ≥90% of correct words were left alone, so the app shows a pitch-contour chart instead
      of a verdict.
    - The experiment script is in git history before the DI redesign
      (`backend/scripts/stress_experiment.py`).
- **Whisper** auto-corrects towards real words, so it's only used to transcribe free speech.
- **gemma3:4b** gives good minimal rewrites, but its grammar explanations are often wrong, so
  none are shown. Replies take about 7 s, and grammar checks about 8 s more.

---

## Direct Instruction design (decided 2026-10-18)

### Why change
Practice history up to 2026-09-30:
- **Flashcards:** 981 attempts
- **Letters:** 429 attempts
- **Reading:** 173 attempts
- **Sentences:** 10 attempts
- **Sound pairs:** 0 attempts

With six separate screens and nothing saying what to do next, practice drifted to isolated
words with almost no grammar. Some content also breaks DI sequencing rules:
- Alphabet lesson 5 introduces Ж, Ш, Щ and Ы together.
- The starter deck introduces words by theme rather than by what a sentence needs.

### About DI
DI is Engelmann and Becker's design method. It is not the Berlitz "Direct Method".

- **Evidence:** it comes mostly from school reading, maths and language for children: Project
  Follow Through, and the Stockard et al. 2018 meta-analysis (328 studies, average effect
  about 0.6 SD).
- **Fit with learning research:** its principles match well-supported findings on retrieval
  practice, spacing, interleaving and mastery learning.
- **Language courses:** Pimsleur and Michel Thomas are close relatives.
- **Main weakness of language drills:** meaning-free drilling transfers poorly to real use.
  So every response here carries meaning (picture or English cue), and each lesson ends in
  real use.

| Principle | In this app |
|---|---|
| Faultless communication: examples allow only one interpretation; learner errors mean the lesson needs fixing | Example sets are designed by sameness/difference; item error stats point to content to revise |
| Sameness and minimum difference | Positive examples vary widely; non-examples differ by one feature (Это кошка / Я вижу кошку) |
| Model → Lead → Test, plus a delayed test | Hear it, say it along with the native voice, answer alone, get tested again later |
| Fixed correction procedure | On an error: model, lead, retest, back up 2 items, queue a delayed test |
| Firm-up to mastery | An exercise repeats until about 90% is right on the first try. Mastery tests every 5 lessons. Placement test on first launch |
| Track design | Each lesson mixes 4–6 short exercises from different tracks; about 10–20% new, the rest firm-up and cumulative review |
| Separate confusable items | Confusable items are introduced at least 5 lessons apart and contrasted only once each is firm |
| Brisk pace, many responses | Hands-free: the mic opens after each prompt and answers are marked instantly |

### Decisions
1. **Cues:** images and emoji are used wherever they make meaning clear without English.
   English cues are used otherwise.
2. **Old screens stay** as a **Practice** area. All content (letters, decks, sentences, pairs,
   conversation) stays reachable for review at any time. The lesson path becomes the main
   route.
3. **Hard mastery gates:** the next lesson unlocks only after the current one is passed. A
   failed mastery test leads to remedial lessons built from the items you missed.
4. **Lesson length:** aim for about 20 minutes, but content decides.

### Tracks
| Track | Content |
|---|---|
| A. Sounds & script | Re-sequenced so confusable letters are separated; mostly skipped via placement |
| B. Sentence frames (core) | Это ___ → Это не ___, это ___ → Где ___? → мой/моя/моё → У меня есть ___ → Я вижу ___ (accusative) → present tense → one case at a time |
| C. Vocabulary | 3–5 words per lesson, introduced only when a frame needs them and used the same day |
| D. Listening discrimination | Hear a sentence, then choose the picture or meaning, including grammar minimal pairs |
| E. Sound contrasts | Sound pairs, contrasted only after both members are firm |
| F. Numbers | Its own daily track |
| G. Application | A short scripted dialogue every lesson; at the end of each unit, a conversation limited to taught words and grammar |

### Curriculum checks (tests that fail the build)
- At most about 20% new items per lesson
- At least 3 tracks per lesson
- No item used before it's introduced
- Each new item reviewed in at least 3 later lessons
- Confusable items introduced at least N lessons apart
- Stress marks on all multi-vowel words
- Inflected forms checked with pymorphy3 (offline morphology)

pymorphy3 gives no stress, and stress moves in some forms (вода́ → во́ду), so stress marks are
written by hand.

### Phases
8. **Answer-checking calibration ✅ (done 2026-10-18).** Can the speech stack tell grammar minimal pairs
   apart? The script is `backend/scripts/answer_check_experiment.py`. The test set was 20 sets of
   grammar minimal forms, spoken by 4 Silero voices and macOS Milena (230 recordings). Each
   recording was scored against every form in its set, and the best match counted as what was said.

   | Rule | Native accuracy | Time per check |
   |---|---|---|
   | **Whole-utterance CTC likelihood (with reduction/devoicing variants)** | **92.2%** | 0.7 s |
   | Mean letter score of each candidate | 88.3% | 1.3 s |
   | Whisper transcript, nearest candidate | 80.0% | 1.4 s |

   - **Decision:** lessons check spoken answers by **forced choice on likelihood** against the
     item's expected answer and its distractors. The expected answer must also reach a letter
     score of 50, so mumbling isn't accepted.
   - **Reliable contrasts (9–10/10)**, which can decide a spoken answer:
     - accusative, genitive, prepositional and instrumental endings
     - plural
     - «не»
     - меня/мне
     - past-tense gender
     - говорю/говорит/говорят
     - тут/там
     - different words
   - **Unreliable contrasts:**
     - adjective endings -ый/-ая/-ое (8/15)
     - мой/моя/моё (12/15)
     - person endings that differ only in a final consonant, e.g. читаю/читаем/читают (20/25)

     These are taught and tested with listening and choose-the-form exercises. They are never the
     only difference between a spoken answer and a distractor.
   - **Whisper** turns ungrammatical speech into grammatical text ("с молоко" → "с молоком" for 4 of 5
     voices), so it's never used to judge grammar.
   - **English voice:** an English voice reading made-up spellings scored 9/14. That's a weak stand-in
     for a real accent, so the lesson player has an **"I said it right"** override, which is logged
     separately.
   - **Course content check:** `--lessons` replays every speaking item in the course. Each answer
     spoken by 2 native voices must be accepted, and each distractor said instead must be rejected.
     The pilot lessons pass 388/388.
   - **pymorphy3** generates the inflected forms correctly. It gives no stress, so stress marks
     stay hand-written.
9. **Lesson engine ✅ (done 2026-10-18).**
   - **Content:** lessons are JSON files in `backend/data/course/`, checked on load (`course.validate_lesson`).
     An exercise has a `track`, a `type` (`teach`, `say`, `choose` or `dialogue`) and `items`.
     - **Spoken items:** `answer`, `cue` (emoji), `english`, an optional `ask` (question audio),
       `distractors` (likely wrong answers for the forced choice) and `accept` (other right answers).
     - **Listening items:** `audio`, `options` and `correct`.
   - **Runtime** (`frontend/src/LessonPlayer.tsx`):
     - **teach:** each item is modelled and repeated, then tested straight away and again after
       the next item. A shuffled cold pass at the end holds the tries that count.
     - **Corrections:** on a miss, the answer is modelled, the learner says it after the voice,
       2 items are re-tested, and the missed item comes back 3 steps later.
     - **Firm-up:** a round passes at 90% right first time. Otherwise the same exercise repeats in
       a new order.
     - **Hands-free:** the mic opens after each prompt and stops on silence.
     - **Override:** "I said it right" (`O`) counts a miss as right. The override is stored.
   - **Gates and storage:**
     - Hard gates are enforced on the server: a locked lesson returns 403 for both content and checks.
     - Progress is kept in `course_progress`. Every try (`first`, `practice`, `retest`, `delayed`) is
       kept in `course_results` under a stable item key, ready for review scheduling.
   - **Answer check** (`speech/answers.py`):
     - **Correctness:** forced choice by likelihood, with letter score ≥ 50 on the expected answer.
     - **"That sounded like …":** a wrong candidate is named only when the model's unsteered
       reading of the audio matches it, so a random word isn't reported as a distractor.
     - **Letter statistics:** spoken lesson answers feed them (source `lesson`).
   - **3 pilot lessons:**
     1. «Это …»
     2. Да/нет with «не»
     3. «Где …?» with тут/там

     Each has 6–8 exercises across 5 tracks, with numbers 1–5 and a dialogue in every lesson.
   - **Navigation:** 📘 Lessons is the default screen. The original screens are grouped under
     **Practice**.
   - **Verified in the real app:**
     - **Setup:** headless Chromium with a fake microphone playing native audio.
     - **Spoken items:** model → repeat → cold test passes, and a wrong answer runs the full
       correction.
     - **Listening:** a miss gets its delayed re-test, and 5/6 gives 83%, so a firm-up round.
     - **Dialogue:** partner turns play and advance by themselves.
   - **Not yet done:**
     - The pilot lessons were written before the scope and sequence, and Phase 10 may re-order them.
     - There's no "choose the written form" exercise yet. It's needed for the contrasts the checker
       can't hear.
10. **Scope and sequence plus lessons 1–20.** A track map for about 60 lessons, the curriculum
    checker, and pymorphy3 validation.
11. **Mastery and review.** Mastery tests, placement, remediation, and FSRS-due items in each
    lesson's review block.
12. **Lessons become the main route.**
    - Home becomes "Today's lesson"; the old screens move under Practice
    - Starter words are linked to the lessons that introduce them
    - The dashboard shows the lesson path, mastery test results and per-track accuracy
13. **Lessons 21–60 and constrained conversation.** The partner is told the taught words and
    grammar, and unknown words in its replies are flagged.
