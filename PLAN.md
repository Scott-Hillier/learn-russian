# Learn Russian: Plan

> Picking this up? Start with [HANDOFF.md](HANDOFF.md): it covers what's done, what's left, and how to
> add and verify lessons.

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
3. **Mastery gates:** hard at first. On 2026-10-20 the user switched to **soft gates**: lesson 1's first
   exercise has 3 items, so one miss (67%) failed the round, and the user would rarely get through. Now
   every finished round moves on, and a round below 90% offers "Go again" instead of forcing it. Taking a
   unit's mastery test unlocks the next unit, pass or fail. The fix-up lesson and the retake are optional.
   Misses still drive review.
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
10. **Scope and sequence, curriculum checker, lessons 1–10 ✅ (done 2026-10-18).**
    - **Scope and sequence:** see the table below.
    - **Curriculum checker** (`backend/app/curriculum.py`, run by `tests/test_curriculum.py`): words are
      compared by lemma via pymorphy3. The build fails if:
      - a lesson has fewer than 3 tracks, or no review exercise from lesson 2 on
      - a word isn't in the pymorphy3 dictionary (catches typos)
      - a lesson brings more than 8 new words
      - a teach exercise has more than 5 items
      - a word is said before it has been modelled in a teach exercise
      - a new word doesn't come back in at least 2 of the next 5 lessons
      - confusable items are introduced too close together (`data/course/confusables.json`)
      - a distractor differs from the answer only by a contrast the checker can't hear
    - **Filled in when lessons load:**
      - Each spoken item's distractors include the other answers in its exercise.
      - `"review": N` exercises take N spoken items from 1, 2, 3, 5, 8… lessons back.
    - **New exercise item:** choose the written form (`prompt` "___ сок", options мой/моя/моё).
      The full sentence plays after answering. Contrasts that speech can't judge are taught this way.
    - **Lessons 1–10** are rewritten in DI order:
      - тут (3) is firm before там (5)
      - он (7) → она (8) → оно (9), each contrasted with the ones before
      - кто/что (6)
      - мой/моя/моё (10)
    - **Speech check of the lessons:** every speaking item and every distractor, spoken by 2 native
      voices, comes out as expected (1,576/1,576 checks). That includes он/она/оно, which are
      reliable as whole short sentences.
    - **Verified in the real app:** the written-form exercise ran through to a delayed re-test and
      a firm-up round. Two display bugs were fixed: stress marks on options, and a doubled accent on ё.

10a. **Answer checking for a learner's voice ✅ (done 2026-10-20).** The learner can't supply reference
    recordings (they aren't a native speaker), so the checker was tuned on simulated learner speech instead.
    - **Benchmark** (`backend/scripts/learner_benchmark.py`): every speaking item in the course is said
      three ways (the answer, its closest distractor, and an unrelated answer from another lesson) under
      7 conditions:
      - **native:** 5 Silero voices and macOS Milena
      - **slow:** x-slow speech
      - **pauses:** each word said separately, with 0.3–0.8 s gaps
      - **syllables:** words sounded out syllable by syllable
      - **stress:** the stress put on the wrong syllable
      - **accent:** English-speaker substitutions (ы → и, щ → ш, х → к, no ь)
      - **english:** 12 English voices reading English-style respellings ("ya vee-zhoo kosh-koo")

      Every recording goes through a random laptop channel (level, mic EQ, room echo, fan noise) and
      Opus compression, as the browser's recorder does. Scores are saved once (`collect`), so decision
      rules can be compared offline (`analyse --grid / --fit-grid`).
    - **What it found (96 items, 2,016 recordings):**
      - Forced choice was already robust to learner speech: 99% of right answers accepted, 100% of
        distractors rejected.
      - The weak spot was the reverse: an unrelated sentence was accepted 7–9% of the time, because the
        mean letter score is easily fooled ("Машина там" scored 75 as «мама»).
    - **New rule** (`app/speech/answers.py`):
      - **Mode:** candidates are scored in *learner mode* (`analyse_word(learner=True)`): ы/и, щ/ш, х/к
        and й/и are accepted, and ь/ъ may be dropped. If that makes the answer and a distractor sound the
        same (был/бил), strict spelling is used.
      - **Fit:** the answer must *fit* the audio. Its forced alignment may fall at most 40 below the model's
        free reading (log-likelihood per 100 frames).
      - **Letter score:** at least 30 in learner mode. The feedback shown still uses strict letters.
      - **"Say it again":** a fit between −55 and −40, or a distractor winning by less than 2.5, gets
        "say it again" once instead of a verdict.

      | | Before | After |
      |---|---|---|
      | Unrelated sentence accepted (native / learner-like) | 8.3% / 7.3% | 1.0% / 0.8% |
      | Right answer accepted (learner-like) | 99.2% | 99.2% |
      | Distractor rejected (learner-like) | 100% | 100% |
      | Right answer accepted (heavy English accent) | 71.9% | 79.2% |
    - **Lessons 1–20 with native voices:** 3,601/3,602 judged as expected. The miss, «маму» heard as
      «мама» from one voice, now gets "say it again".

10b. **Lessons 11–20 ✅ (done 2026-10-20).**
    - **Content, in DI order:**
      - твой/твоя/твоё (form choice, plus whole sentences with мой/твой)
      - папа and дверь learned with their gender
      - «Меня зовут …», played as Анна 👩 or Иван 👨
      - present tense я → ты → он/она, then contrasted (знать, понимать)
      - говорить with по-русски / по-английски
      - «Я хочу …» and «Я вижу …» with the accusative -а → -у
      - a unit review with two dialogues
    - **Also new:** «Ещё раз, пожалуйста», хорошо, тоже, пока, очень приятно, and numbers 11–30.
    - **Stress fixes:** lessons 3–10 had молоко and телефон stressed wrongly (мол+око, тел+ефон). They are
      now молоко́ and телефо́н. The number speller had четыр+надцать; it's now четы́рнадцать.
    - **Counting in sentences (2026-10-27, the learner's request):** the «Сколько?» items in lessons 6–18
      used to take a bare number. They now ask «Сколько кошек?» and take «Тут пять кошек.», using taught
      countable nouns only. The noun forms come in with the gender lessons: 5 and up (L6), он-words with 1
      and 2–4 (L7), она-words (L8), оно-words (L9), then mixed. Lessons 6–9 are teach exercises, so each
      form is modelled first. Wrong-form distractors are used only where the checker can hear the
      difference. один/одна/одно is not graded, and neither is яблоко/яблока, which sound the same. Native
      voices: 1448/1460 judged as expected. Of the 12 misses, 5 were right answers that got "say it
      again", and 6 were those two inaudible distractors, now removed.

### Scope and sequence
Each new item comes in only after what it depends on is firm. Confusable items are introduced
apart and contrasted afterwards (тут → там, он → она → оно). Every lesson also has review, numbers
and a dialogue.

| Lessons | Sentence frames (core track) | New words, about 3 per lesson | Numbers |
|---|---|---|---|
| 1 | «Это …» | дом, кошка, собака | 1–3 |
| 2 | «Это …?» — «Да, это … / Нет, это не …, это …» | машина, книга, хлеб | 4–5 |
| 3 | «Где …?» — «… тут» | ключ, телефон | 6–7 |
| 4 | Greetings: привет / здравствуйте, спасибо, пожалуйста | | 8–10 |
| 5 | «… там», then тут/там contrasted | паспорт, сумка | 1–10 mixed |
| 6 | «Кто это?» (people and animals) vs «Что это?» | мама, брат, сестра, друг | «Сколько кошек?» — «Тут пять кошек.» (5 and up) |
| 7 | он (consonant ending) | стул, сок | counting: один дом, два ключа (он-words, 1–4) |
| 8 | она (-а), then он/она contrasted | рыба, вода | counting: одна кошка, две книги (она-words) |
| 9 | оно (-о), then all three contrasted | молоко, яблоко, окно | counting: одно яблоко, два яблока, семь окон |
| 10 | мой / моя / моё (form choice, plus whole sentences) | | counting, 1 / 2–4 / 5+ mixed |
| 11 | твой / твоя / твоё; «Это твой …?» — «Да, это мой …» | | 11–12 |
| 12 | Gender to learn with the word: папа (он), дверь (она) | папа, дверь | 13–15 |
| 13 | «Как тебя зовут?» — «Меня зовут …»; я / ты (played as Анна / Иван) | | 16–17 |
| 14 | Present tense, я form: я знаю, я понимаю, я не понимаю | | 18–19 |
| 15 | ты form: ты знаешь? ты понимаешь? | ещё раз, хорошо | 20 |
| 16 | он/она form, then я/ты/он contrasted | тоже | counting |
| 17 | говорить: говорю / говоришь / говорит | по-русски, по-английски, немного | counting |
| 18 | «Я хочу …» with accusative -а → -у (воду, рыбу), masculine unchanged | чай, кофе | counting |
| 19 | «Я вижу …» with accusative for people and animals (маму, папу, кошку) | | 20–30 |
| 20 | Unit review dialogues: meeting someone, at a friend's | пока, очень приятно | 1–30 |
| 21 | мы / вы / они (говорить spoken; знать/понимать endings by form choice) | | 40, 50 |
| 22 | в / на + prepositional: в доме, на столе | стол | to 50 |
| 23 | «Я живу в …»: жить, в Москве / в Лондоне | Москва, Лондон | 60, 70 |
| 24 | Nominative plural (-ы / -и), мои, они | | 80–100 |
| 25 | Unit review: где ты живёшь? | | to 100 |
| 26 | «У меня есть …» (the thing stays nominative) | | |
| 27 | «У меня нет …» + genitive | | |
| 28 | у него / у неё / у вас | | |
| 29 | In a shop: «У вас есть …?», «… нет», и | магазин, сыр | |
| 30 | Unit review | | |
| 31 | идти + в + accusative; где vs куда; домой; «А ты?» | школа | |
| 32 | ехать; на работу / на работе | работа | |
| 33 | «Который час?» — час / часа / часов | | |
| 34 | «Какой сегодня день?» | понедельник, вторник, среда | |
| 35 | The rest of the week, завтра; unit review | четверг … воскресенье | |
| 36 | «Мне нравится …» (мне / тебе) | | |
| 37 | в субботу (days with в + accusative); делать | | |
| 38 | «Сколько стоит?» — рубль / рубля / рублей | | prices |
| 39 | In a café: «Мне …, пожалуйста», «Счёт, пожалуйста» | кафе, счёт | |
| 40 | Unit review | | |
| 41 | Past tense: был / была (as Иван / Анна) | вчера | |
| 42 | -л / -ла with known verbs | | |
| 43 | -ли for more than one; были | кино | |
| 44 | с + instrumental: кофе с молоком, с братом | сахар | |
| 45 | Unit review | | |
| 46 | работать (endings by form choice) | | |
| 47 | читать + accusative | газета | |
| 48 | «Можно …?» — «Да, конечно» | | |
| 49 | «Как дела?» — хорошо / нормально / плохо | | |
| 50 | Unit review: coffee with a friend | | |
| 51 | Future: буду + infinitive; past / present / future contrasted | | |
| 52 | «Сейчас …, потом …» | потом | |
| 53 | большой / маленький (endings by form choice) | | |
| 54 | хороший / плохой / новый | погода | |
| 55 | Unit review | | |
| 56 | любить + accusative, contrasted with «нравится» | | |
| 57 | Asking the way: извините, налево, направо, прямо | | |
| 58 | «Сколько тебе лет?» — год / года / лет | | |
| 59 | «До свидания»; a day out in three dialogues | | |
| 60 | Final review | | |
11. **Mastery and review ✅ (done 2026-10-20).**
    - **Units and tests:** every 5 lessons make a unit, and each unit ends with a **mastery test**
      (`course.build_test`):
      - 3 spoken and 2 listening/reading items from each lesson, sentences first
      - one try each, no modelling and no corrections
      - 90% to pass
      - each attempt gets a fixed sample, and a retest always includes the items missed last time

      Lesson 5n+1 unlocks once unit n's test has been taken (soft gate since 2026-10-20; `course_tests` table).
    - **Remediation:** a failed mastery test gives a **fix-up lesson** built from the missed items: spoken
      ones are taught again (model, lead, test), and the rest are redone. After it, the test can be retaken.
      Both are optional since the soft gates of 2026-10-20.
    - **Placement:** any unit's test can be taken once the unit before it is passed, so a learner can
      **test out**.
      - **Pass:** the unit's lessons are marked passed (`placed`), and the next test can be tried straight
        away.
      - **Fail:** just start that unit, with no fix-up lesson.

      A fresh learner is offered this on the Today screen and above lesson 1.
    - **Answer checks:** every item records where it was written (`src`), so answers given in reviews,
      tests and fix-ups are checked against their original item. Items in locked lessons can only be
      checked inside their unit's test.
    - **Review driven by errors:** a lesson's review block (`Course.review_items`) is filled in this order:
      1. Items missed in their last few counted tries (first tries, delayed re-tests, test answers), worst
         first. These take up to half the block.
      2. Lesson words that are **due in the flashcards**, up to a third. Answering one there counts as its
         flashcard review (Good, or Again if wrong).
      3. The spaced items, from 1, 2, 3, 5, 8… lessons back.
12. **Lessons become the main route ✅ (done 2026-10-20).**
    - **🏠 Today** is the new home screen. It shows:
      - the next step (lesson, test or fix-up), started with Enter
      - due flashcards
      - the lesson path, with tests between units
      - right-first-time accuracy per track (`/api/course/stats`)
      - the items to work on
      - test history
    - **Starter words are linked to lessons:** `course.lesson_for` matches a single word to the lesson that
      first introduces it, by lemma (67 starter words so far).
      - Flashcards show "📘 Lesson N".
      - Passing a lesson, or testing out of its unit, starts the schedule of its still-new built-in cards.
        They're rated Easy without counting as a review, because the lesson already drilled them.
13. **Lessons 21–60 and constrained conversation ✅ (done 2026-10-20).**
    - **Lessons 21–60** follow the scope table above.
      - **Curriculum checker:** every lesson passes.
      - **Native-voice speech check:** 8,397 of 8,404 checks came out as expected.
      - **The misses:** six hinged on a short ending: unstressed final а/у (в школу / в школа,
        нравится работа / работу, нет брата / брат) or видел/видела before кошку.
      - **The fix:** those six explicit distractors were removed. The same contrasts are still taught by
        choosing the written form.
    - **Curriculum checker fixes:**
      - Past-tense gender (знал/знала) is no longer flagged as unhearable; only present-tense -ать endings
        are.
      - Any two forms of one adjective or possessive are flagged.
      - Lemmas prefer the verb over a participle (читаем), and большая is read as большой.
    - **Conversation:** the 🤖 partner has a new default level, "Only words from my lessons".
      - The partner is given the lemmas and the lesson goals from the lessons passed so far.
      - Words in its reply outside that set are listed in `unknown` and underlined in the chat.
      - A reply with unknown words gets up to two retries that name them, and the reply with the fewest is
        kept.
      - A new scenario, "At a friend's place", uses lesson content.
