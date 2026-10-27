# Handoff: where the Direct Instruction redesign stands

Last updated 2026-10-20. Read this first, then [PLAN.md](PLAN.md). PLAN.md covers the method, the
decisions, the 60-lesson scope and sequence, and implementation notes for each phase.

## The user and the project
- **The user** is a complete beginner learning Russian alone. There is no tutor or native speaker
  to practise with.
- **Constraints:**
  - Fully offline at runtime.
  - Apple M1 with 8 GB of RAM.
  - Never add a cloud dependency.
- **Method:** on 2026-10-18 the user chose **Direct Instruction** (Engelmann), and decided:
  - Emoji and picture cues where they make meaning clear.
  - Keep every old screen as a **Practice** area: all content must stay reviewable at any time.
  - Mastery gates: **soft since 2026-10-20** (the user's change; hard gates failed a round for one miss
    in 3). Every finished round moves on, a mastery test only has to be taken, and misses drive review.
  - Lessons of about 20 minutes, but content decides the length.
- **Display rules:** no transliteration on study screens; English meanings are fine. Letter cards
  are the one exception. On lesson screens the order of importance is **Russian → English → picture**
  (the user's rule, 2026-10-20). Russian is the largest, and it is hidden only while it's the answer
  being asked for. The user works on a desktop only, so the lesson player is laid out wide
  (`LessonPlayer.tsx` `StepView`). Numbers have no emoji, just digits. Pictures must be easy to tell
  apart: 🐱/🐶, not 🐈/🐕.
- **Answer checking:** the user's own recordings can't define what a right answer sounds like, because
  they aren't a native speaker (their words, 2026-10-20). The checker is tuned on simulated learner
  speech instead (`backend/scripts/learner_benchmark.py`). Don't ask the user for reference recordings.
- **Right words, not pronunciation (the user's rule, 2026-10-27):** "if I get the word right then we
  can move on … it's more important that I learn many words than a few I can say perfectly". The
  checker grades which answer was said, not how well, and there's no "say it again". A miss is corrected
  once (model, say it after me, one delayed re-test) and then left to review. Don't add spoken
  distractors that hinge on a short ending.
- **Workflow:** after finishing a phase, update PLAN.md's implementation note, commit to `main`, and
  push to `origin` (github.com/Scott-Hillier/learn-russian). The user has authorised this. Commit
  messages end with the Co-Authored-By line used in the existing history.

## Done
| Phase | What | Commit |
|---|---|---|
| 8 | Calibration of answer checking: forced choice on CTC likelihood wins (92% native) | 3251c9c |
| 9 | Lesson engine: player, correction procedure, firm-up rounds, hard gates, hands-free mic | 9220f4b |
| 10 | Scope and sequence, curriculum checker, lessons 1–10 | fb29105 |
| 10a | Answer checking tuned on simulated learners: learner mode, fit gate, "say it again" | e244d69 |
| 10b | Lessons 11–20; stress fixes (молоко́, телефо́н, четы́рнадцать) | ee38ea9 |
| 11–13 | Mastery tests, fix-up lessons, placement, error-driven review; Today screen, word links, dashboard; lessons 21–60; conversation limited to taught words; stress fixes in sentences | c7c2a0d |
| — | Soft gates (user's request): finished rounds move on, a taken test opens the next unit | 309ee6d |
| — | Counting answered in sentences («Тут пять кошек.», lessons 6–18); a far-off miss is sounded out slowly, then at normal speed | (this commit) |

## What's left
All phases in PLAN.md are built. In order of value:
1. **The user goes through the course.** Two things to watch:
   - **Misjudged answers.** `course_results.override = 1` in `backend/userdata/progress.db` marks every
     "I said it right". Group them by `item_key` to find items the checker misjudges for this learner.
   - **Content that needs fixing.** `Course.stats()["work_on"]` (the Today screen) shows items the learner
     keeps missing. In DI, a learner's errors mean the lesson needs fixing.

   Don't write to the user's `progress.db` or `recordings/` from tests or experiments.
2. **A native speaker's review of lessons 11–60.** I wrote all the Russian. The checks catch typos,
   missing stress marks, untaught words and form errors, but not unnatural phrasing. The riskiest spots:
   - dialogue lines
   - «Мне воду, пожалуйста»
   - the age and price agreement items
3. **Known gaps in the player:**
   - A "say it after me" step has one try by design; a miss hears the model and moves on.
   - The N/M counter only counts the cold final pass during teach exercises.
4. **Beyond lesson 60:** the next obvious steps are more cases (dative: «мне нужно», «брату»), verbs of
   motion with «на», «потому что», and «который». Extend the scope table first, then the curriculum
   checker keeps the content honest.

## How the course works (code map)
| File | Role |
|---|---|
| `backend/data/course/NNN.json` | One lesson per file (1–60). **This is the source of truth.** All lessons came from throwaway generators that weren't kept, so edit the JSON directly. |
| `backend/data/course/confusables.json` | Groups of words that must be introduced N lessons apart |
| `backend/app/course.py` | See the next table. |
| `backend/app/curriculum.py` | DI rule checker, run by `tests/test_curriculum.py`. Words are compared by lemma (pymorphy3, with fixes for participles and большая). `introductions()` maps each lemma to its first lesson. |
| `backend/app/speech/answers.py` | Returns `reason` on a miss (`other` / `fit`), so the player can explain green letters with a red verdict. Checks a spoken answer for the right words: forced choice on likelihood in learner mode (strict when learner mode makes a distractor sound the same), near ties (`TIE_MARGIN`) go to the learner, and a loose fit gate (`MIN_FIT`) rejects unrelated speech. Letter scores only colour the feedback. |
| `backend/app/speech/pronunciation.py` | `log_probs`, `likelihood(..., learner=)`, `free_likelihood`, `greedy_text` and `score(..., logp=, learner=)`: one model pass, many scorings. `LEARNER_VARIANTS` and `learner_form` live here. |
| `backend/app/routes_course.py` | Endpoints:<br>• `/api/course`, `/{id}`, `/{id}/rounds`, `/{id}/restart`<br>• `/{src lesson}/check` (form fields `exercise`, `item`, optional `test`)<br>• `/stats`<br>• `/tests/{unit}`, `/tests/{unit}/finish`, `/tests/{unit}/remedial`, `/tests/{unit}/remedial/rounds` |
| `backend/app/chat.py` | Conversation partner. Level `lessons` passes `Course.taught()` into the prompt, flags `unknown_words`, and retries replies that stray. |
| `frontend/src/HomeView.tsx` | 🏠 Today: next step, path, accuracy per track, items to work on, tests |
| `frontend/src/LessonPlayer.tsx` | Step queue: model, lead, test, and the correction procedure. Handles firm-up rounds and the hands-free mic. A far-off miss (another answer, or score < 50) is modelled slowly, then at normal speed. Test mode (`lesson.kind === "test"`): one try per item, no corrections, one result at the end. |
| `frontend/src/CourseView.tsx` | Lesson and test list, the placement offer, and the fix-up lesson. Opens and starts what Today asks for (`start` prop). |
| `backend/scripts/answer_check_experiment.py` | The Phase 8 experiment, plus `--lessons [--from N]`: a native-voice check of every course item |
| `backend/scripts/learner_benchmark.py` | `collect`: simulated learner speech for every course item. `analyse`: replays decision rules. |

**Out-of-date pages (2026-10-20):** a tab opened before items carried `src` checked
[lesson, exercise, position]. In a per-learner review block that is a different item: 🐶 was shown while
«Это дом.» was checked. `/check` now refuses (409) a position inside a review exercise, and an item `key`
that doesn't match. `/api/health` reports the UI `bundle`, and `App.tsx` shows a reload banner when the page
runs a different one. `index.html` is served `no-cache`.

Since 2026-10-20, a one-noun answer («соба́ка») also accepts «Это соба́ка.», with framed distractors so
«Это ко́шка.» can't pass (`course._this_is`). Picture-only listening options get English `labels` from the
vocabulary items that use the same picture (`_picture_words`). Only lessons 1–3 were re-simulated after the
framed distractors were added. Run `answer_check_experiment --lessons` over the rest when there's time.

**What `course.py` does:**

| Area | Functions |
|---|---|
| Loading | Loads and validates lessons. Fills in distractors and spaced `"review": N` items, and gives every item its `src` ([lesson, exercise, item]). |
| Lessons | Soft gates, rounds, and the 90% mark a round needs to count as passed. |
| Units and tests | `build_test`, `build_remedial`, `Course.test` / `finish_test` / `remedial`, and placement |
| Review | `Course.review_items`: recent misses first, then flashcards that are due, then spaced items |
| Word links | `lesson_for`, plus starting the flashcard schedule of a passed lesson's words |
| Stats and conversation | `Course.stats` and `Course.taught` |

### Lesson format, briefly
- **Exercise fields:** `track` (`script`, `frames`, `vocab`, `listening`, `sounds`, `numbers`,
  `dialogue` or `review`), `type`, `title`, `instruction`, and `items` (or `"review": N`).
- **`teach` / `say` items:** `answer` (with `+` before the stressed vowel; ё needs no mark), `cue`
  (emoji), `english`, and optionally `ask` (question audio), `distractors` and `accept`.
- **`choose` items:**
  - **Listening:** `audio`, `options` and `correct`.
  - **Choose the written form:** `prompt` ("___ сок"), Russian `options`, `correct`, and `audio`
    (the full sentence, played after answering).
- **`dialogue` items:** `{"speaker": "partner", "line": …}` turns, plus learner turns that work like
  `say` items.
- **Role-play:** past-tense and «меня зовут» items use the cues 👩 Анна / 👨 Иван, so the learner knows
  which gender form to say.

### Rules new content must pass
1. `cd backend && .venv/bin/python -m pytest -q`. This includes the curriculum checker:
   - at least 3 tracks per lesson, and a review exercise from lesson 2 on
   - at most 8 new lemmas per lesson, and at most 5 items per teach exercise
   - every word in the pymorphy3 dictionary
   - no word said before it has been taught
   - each new word back in at least 2 of the next 5 lessons
   - confusable items kept apart
   - no distractor that differs from the answer only by a contrast speech can't judge
2. `cd backend && .venv/bin/python -m scripts.answer_check_experiment --lessons --from N`. Every
   check should come out "as expected".
   It takes about 4 minutes per lesson, so run it in the background.
3. **Contrasts speech can't judge** go in `form` or listening exercises, never as the only
   difference between a spoken answer and a distractor:
   - adjective and possessive endings (any two forms of one adjective)
   - мой/моя/моё
   - present-tense -аю / -аем / -ают / -ает
4. **Contrasts speech judges reliably:**
   - case endings
   - plural
   - не
   - меня/мне
   - past-tense gender
   - говорю/говорит/говорят
   - тут/там
   - он/она/оно in short sentences
5. **Stress:** check each new word form by hand. pymorphy3 gives none, and two wrong stresses slipped
   into lessons 3–10 before (fixed 2026-10-20).

## Verifying in the real app (no browser tools needed)
- **Start a test server:**
  - Command: `PROGRESS_DB=<scratch>/test.db .venv/bin/uvicorn app.main:app --port 8010` from
    `backend/`. Poll `/api/health` until `"ready":true`.
  - **Always** set `PROGRESS_DB` to a scratch file, so the user's real progress isn't touched.
  - Rebuild the UI first: `cd frontend && npm run build`. `npx tsc -b` type-checks.
- **Skip ahead:**
  - `POST /api/course/{id}/rounds` with `{"exercise": i, "results": [{"key": "x", "step": "first",
    "correct": true}]}` marks an exercise passed.
  - `POST /api/course/tests/{unit}/finish` with every item right passes a test.
- **Browser driving that worked:**
  - Install `playwright-core` into a scratch folder.
  - Launch the cached Chromium at
    `~/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`.
  - Use the flags `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream
    --use-file-for-fake-audio-capture=<16 kHz mono wav> --autoplay-policy=no-user-gesture-required`,
    and grant the `microphone` permission.
  - For the fake microphone, make a WAV from `/api/tts?text=…` padded with silence. The file
    loops, so every answer in a session is the same audio.
- **Memory:** the server, the speech experiment and the learner benchmark each load the models. Run
  only one at a time on the 8 GB machine.

## Known gaps and quirks
- **Repeat steps don't block:** a "say it after me" step has one try; a miss hears the model and
  moves on.
- **Counter during teaching:** the "N/M" counter only counts the cold final pass, so it shows 0/M
  while a teach exercise is introducing items.
- **Content quality:** see "What's left" item 2.
- **pymorphy3** gives no stress, and stress moves in some forms (вода́ → во́ду). Stress marks are
  written by hand.
- **The heavy-accent benchmark condition** accepts about 79% of right answers. It's an English TTS voice
  reading respellings, which is probably harsher than a real learner. The "I said it right" override
  covers the rest.
