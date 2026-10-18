# Handoff: where the Direct Instruction redesign stands

Last updated 2026-10-18. Read this first, then [PLAN.md](PLAN.md). PLAN.md covers the method, the
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
  - **Hard mastery gates.**
  - Lessons of about 20 minutes, but content decides the length.
- **Display rules:** no transliteration on study screens; English meanings are fine. Letter cards
  are the one exception.
- **Workflow:** after finishing a phase, update PLAN.md's implementation note, commit to `main`, and
  push to `origin` (github.com/Scott-Hillier/learn-russian). The user has authorised this. Commit
  messages end with the Co-Authored-By line used in the existing history.

## Done
| Phase | What | Commit |
|---|---|---|
| 8 | Calibration of answer checking: forced choice on CTC likelihood wins (92% native) | 3251c9c |
| 9 | Lesson engine: player, correction procedure, firm-up rounds, hard gates, hands-free mic | 9220f4b |
| 10 | Scope and sequence, curriculum checker, lessons 1–10 | fb29105 |
| (after 10) | `SAVE_RECORDINGS=1` now also saves lesson answers with their item context (`app/recordings.py`) | this commit |

## What's left, in order
1. **Check answer checking on the user's real voice. This is waiting on the user.**
   - **Why it matters:** the only accent evidence so far is an English TTS voice reading made-up
     spellings, which scored 9/14. That's too weak to justify writing 50 more lessons.
   - **The user's step:** they plan to run `SAVE_RECORDINGS=1 ./start.sh` and do lessons 1–3.
   - **What to look at afterwards:**
     - `backend/userdata/recordings/*.json` has the target, the verdict, `heard`, the letter
       score, and the lesson, exercise, item and distractors. The matching `.webm` file sits next
       to each one. Only the last 60 attempts are kept.
     - `course_results` in `backend/userdata/progress.db` has `override = 1` wherever the user
       pressed "I said it right". Those are likely misjudgments.
   - **What to build:** a small script that replays the saved recordings through
     `app.speech.answers.check_answer`, so thresholds can be tuned: `MIN_SCORE = 50`, and
     `HEARD_MATCH = 0.7`, plus whether to add an "uncertain, try again" band.
   - **Data safety:** never write to the user's `progress.db` or `recordings/` from tests or
     experiments.
2. **Phase 10b: lessons 11–20**, following the scope table in PLAN.md:
   - твой
   - gender to learn with the word (папа, дверь)
   - «Меня зовут»
   - present tense я / ты / он
   - говорить
   - хочу + accusative, вижу + accusative
   - a unit review dialogue
3. **Phase 11: mastery and review.**
   - **Mastery test every 5 lessons**, with remedial lessons built from the items missed.
   - **Placement test.** The user already knows the alphabet and about 60 flashcard words, but
     the hard gates currently force a start at lesson 1.
   - **Review driven by errors.** `_review_items` in `app/course.py` is deterministic today.
     It should draw on `course_results` (error rates per `item_key`) and on FSRS-due cards.
4. **Phase 12: lessons become the main route.**
   - A "Today's lesson" home screen.
   - Link starter-deck words to the lessons that introduce them.
   - A dashboard showing the lesson path, mastery test results and accuracy per track.
5. **Phase 13: lessons 21–60, plus a constrained conversation.** Give the Ollama partner the words
   and grammar taught so far, and flag unknown words in its replies (reduce them to dictionary
   form with pymorphy3).

## How the course works (code map)
| File | Role |
|---|---|
| `backend/data/course/NNN.json` | One lesson per file. **This is the source of truth.** Lessons 1–10 were produced by a throwaway generator that wasn't kept, so edit the JSON directly. |
| `backend/data/course/confusables.json` | Groups of words that must be introduced N lessons apart |
| `backend/app/course.py` | Loads and validates lessons. Fills in distractors (the other answers in the exercise) and `"review": N` exercises (from 1, 2, 3, 5, 8… lessons back). Handles gates, rounds and the 90% pass rule. |
| `backend/app/curriculum.py` | DI rule checker, run by `tests/test_curriculum.py`. Words are compared by lemma (pymorphy3). |
| `backend/app/speech/answers.py` | Checks a spoken answer: forced choice on likelihood across answer, `accept` and distractors, plus a letter score of at least `MIN_SCORE`. Reports `heard` only when the model's unsteered reading matches that candidate. |
| `backend/app/speech/pronunciation.py` | `log_probs`, `likelihood`, `greedy_text` and `score(..., logp=)`: one model pass, many scorings |
| `backend/app/routes_course.py` | `/api/course`, `/api/course/{id}`, `/{id}/check`, `/{id}/rounds`, `/{id}/restart`. A locked lesson returns 403. |
| `frontend/src/LessonPlayer.tsx` | Step queue: model, lead, test; the correction procedure (model, repeat, back up 2, delayed re-test 3 later); firm-up rounds; hands-free mic |
| `frontend/src/CourseView.tsx` | Lesson list and overview. **Lessons** is the default screen; the old screens sit under **Practice** in `Layout.tsx`. |
| `backend/scripts/answer_check_experiment.py` | The Phase 8 experiment, plus `--lessons`: a native-voice check of every course item |

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
- Copy the patterns in lessons 7–10: `where()` style items, «Сколько?» counting, `form` items.

### Rules new content must pass
1. `cd backend && .venv/bin/python -m pytest -q`. This includes the curriculum checker:
   - at least 3 tracks per lesson, and a review exercise from lesson 2 on
   - at most 8 new lemmas per lesson, and at most 5 items per teach exercise
   - every word in the pymorphy3 dictionary
   - no word said before it has been taught
   - each new word back in at least 2 of the next 5 lessons
   - confusable items kept apart
   - no distractor that differs from the answer only by a contrast speech can't judge
2. `cd backend && .venv/bin/python -m scripts.answer_check_experiment --lessons`. It must report
   every check "as expected". It takes about 15 minutes for 10 lessons, so run it in the background.
3. **Contrasts speech can't judge** go in `form` or listening exercises, never as the only
   difference between a spoken answer and a distractor:
   - adjective and possessive gender endings
   - мой/моя/моё
   - -аю / -аем / -ают / -ает
4. **Contrasts speech judges reliably:**
   - case endings
   - plural
   - не
   - меня/мне
   - past-tense gender
   - говорю/говорит/говорят
   - тут/там
   - он/она/оно in short sentences

## Verifying in the real app (no browser tools needed)
- **Start a test server:**
  - Command: `PROGRESS_DB=<scratch>/test.db .venv/bin/uvicorn app.main:app --port 8010` from
    `backend/`. Poll `/api/health` until `"ready":true`.
  - **Always** set `PROGRESS_DB` to a scratch file, so the user's real progress isn't touched.
  - Rebuild the UI first: `cd frontend && npm run build`. `npx tsc -b` type-checks.
- **Skip ahead:** `POST /api/course/{id}/rounds` with
  `{"exercise": i, "results": [{"key": "x", "step": "first", "correct": true}]}` marks an exercise
  passed.
- **Browser driving that worked:**
  - Install `playwright-core` into a scratch folder.
  - Launch the cached Chromium at
    `~/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`.
  - Use the flags `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream
    --use-file-for-fake-audio-capture=<16 kHz mono wav> --autoplay-policy=no-user-gesture-required`,
    and grant the `microphone` permission.
  - For the fake microphone, make a WAV from `/api/tts?text=…` padded with silence. The file
    loops, so every answer in a session is the same audio.
- **Memory:** the server and the speech experiment each load the models. Don't run both at once
  on the 8 GB machine.

## Known gaps and quirks
- **Repeat steps don't block:** a "say it after me" step moves on after 2 tries, even if both
  were wrong.
- **Counter during teaching:** the "N/M" counter only counts the cold final pass, so it shows 0/M
  while a teach exercise is introducing items.
- **Review:** review items are fixed per lesson, not adapted to the learner (see Phase 11).
- **Content quality:** I wrote all the lesson Russian. The checks catch typos, missing stress
  marks and form errors, but not unnatural phrasing. A native speaker's review is still worth
  having.
- **pymorphy3** gives no stress, and stress moves in some forms (вода́ → во́ду). Stress marks are
  written by hand.
