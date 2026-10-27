import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ActionBar from "./ActionBar";
import {
  api,
  type AnswerCheck,
  type CourseExercise,
  type CourseItem,
  type CourseLesson,
  type CourseNext,
  type ItemResult,
  type ResultStep,
  type RoundResult,
  type TestResult,
} from "./api";
import { usePref } from "./prefs";
import Stressed from "./Stressed";
import { useHotkeys } from "./useHotkeys";
import { useRecorder } from "./useRecorder";
import { Letters } from "./WordFeedback";

/**
 * Runs a Direct Instruction lesson, one exercise at a time.
 *
 * - teach: each new item is modelled and repeated ("lead"), tested straight away and again after the next
 *   item, then all items are tested cold in a shuffled final pass (those are the tries that count).
 * - say / dialogue: each item is tested once (dialogue partner turns are just played).
 * - choose: hear it, pick the picture.
 * A wrong answer gets the correction procedure: model the answer, repeat it, back up two items, and test the
 * missed item again a few steps later. A round passes at the lesson's pass accuracy on first tries. The gate
 * is soft: every finished round moves on, and below the mark the learner may go again (a shuffled round).
 *
 * A mastery test (lesson.kind "test") runs every exercise straight through: one try per item, no modelling and
 * no corrections, and one result for the whole test at the end. A fix-up lesson ("remedial") runs like a lesson.
 */

type Step =
  | { kind: "lead"; item: number; step: ResultStep; correction?: number }
  | { kind: "test"; item: number; step: ResultStep; correction?: number }
  | { kind: "choose"; item: number; step: ResultStep; correction?: number }
  | { kind: "partner"; item: number };

type Phase =
  "prompt" | "ready" | "listening" | "checking" | "right" | "wrong" | "chosen";

const BACK_UP = 2; // items re-tested after a correction
const DELAY = 3; // steps until a missed item is tested again
const ADVANCE_MS = 900;
const PASS_PERCENT = 90; // mirrors PASS_ACCURACY in backend/app/course.py
const FAR_OFF_SCORE = 50; // a miss scoring below this is far off: the answer is sounded out slowly first
const FAR_OFF_HOLD_MS = 2000; // and stays on screen this long after the model

/** A miss that wasn't close: another answer altogether, or most of the sounds off (usually a forgotten word). */
const farOff = (check: AnswerCheck | null) =>
  !!check && !check.correct && (check.reason === "other" || check.score < FAR_OFF_SCORE);

const pause = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function shuffled<T>(xs: T[]): T[] {
  const out = [...xs];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function buildRound(ex: CourseExercise, round: number, test = false): Step[] {
  const idx = ex.items.map((_, i) => i);
  if (test)
    return idx.map((i) => ({ kind: ex.type === "choose" ? "choose" : "test", item: i, step: "first" }));
  if (ex.type === "dialogue")
    return idx.map((i) =>
      ex.items[i].speaker === "partner"
        ? { kind: "partner", item: i }
        : { kind: "test", item: i, step: "first" },
    );
  if (ex.type === "choose")
    return (round ? shuffled(idx) : idx).map((i) => ({
      kind: "choose",
      item: i,
      step: "first",
    }));
  if (ex.type === "teach" && round === 0) {
    const steps: Step[] = [];
    for (const i of idx) {
      steps.push(
        { kind: "lead", item: i, step: "practice" },
        { kind: "test", item: i, step: "practice" },
      );
      if (i > 0) steps.push({ kind: "test", item: i - 1, step: "practice" });
    }
    return [
      ...steps,
      ...shuffled(idx).map((i): Step => ({
        kind: "test",
        item: i,
        step: "first",
      })),
    ];
  }
  return (round ? shuffled(idx) : idx).map((i) => ({
    kind: "test",
    item: i,
    step: "first",
  }));
}

/** Plays one clip at a time; the promise resolves when it ends (false if it failed or was cut off). */
function useClip() {
  const el = useRef<HTMLAudioElement | null>(null);
  const pending = useRef<((ok: boolean) => void) | null>(null);
  const clip = useMemo(
    () => ({
      play(src: string): Promise<boolean> {
        pending.current?.(false);
        el.current ??= new Audio();
        const a = el.current;
        a.pause();
        a.src = src;
        return new Promise<boolean>((resolve) => {
          pending.current = resolve;
          a.onended = () => resolve(true);
          a.onerror = () => resolve(false);
          a.play().catch(() => resolve(false));
        });
      },
      stop() {
        el.current?.pause();
        pending.current?.(false);
        pending.current = null;
      },
    }),
    [],
  );
  useEffect(() => () => clip.stop(), [clip]);
  return clip;
}

interface Props {
  lesson: CourseLesson;
  onExit: () => void;
  /** The lesson, fix-up lesson or test is over; `next` is what to go to (null: stay on the course page). */
  onDone: (next: CourseNext | null) => void;
}

export default function LessonPlayer({ lesson, onExit, onDone }: Props) {
  const isTest = lesson.kind === "test";
  const [exIndex, setExIndex] = useState(
    lesson.exercise >= lesson.exercises.length ? 0 : lesson.exercise,
  );
  const [round, setRound] = useState(0);
  const [queue, setQueue] = useState<Step[]>(() =>
    buildRound(lesson.exercises[exIndex], 0, isTest),
  );
  const [pos, setPos] = useState(0);
  const [phase, setPhase] = useState<Phase>("prompt");
  const [check, setCheck] = useState<AnswerCheck | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [summary, setSummary] = useState<RoundResult | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [silentTries, setSilentTries] = useState(0);
  const [unclear, setUnclear] = useState(false); // this step already got one "say it again"
  const [leadTries, setLeadTries] = useState(0);
  const [handsFree, setHandsFree] = usePref("handsfree", true);
  const [paused, setPaused] = useState(false);
  const results = useRef<ItemResult[]>([]);
  const lastFirst = useRef<number | null>(null); // results index of the last counted miss (for "I said it right")
  const clip = useClip();

  const ex = lesson.exercises[exIndex];
  const step = queue[pos] as Step | undefined;
  const item: CourseItem | undefined = step ? ex.items[step.item] : undefined;
  const listenFirst = handsFree && !paused;

  const record = (r: ItemResult) => {
    results.current.push(r);
    return results.current.length - 1;
  };

  const next = useCallback(() => {
    setCheck(null);
    setPicked(null);
    setLeadTries(0);
    setSilentTries(0);
    setUnclear(false);
    setPhase("prompt");
    setPos((p) => p + 1);
  }, []);

  const finishRound = useCallback(async () => {
    try {
      if (isTest && exIndex + 1 < lesson.exercises.length)
        return startExercise(exIndex + 1, 0, true); // a test runs straight on; results are kept until the end
      if (isTest) setTestResult(await api.courseTestFinish(lesson.id, results.current));
      else if (lesson.kind === "remedial")
        setSummary(await api.courseRemedialRound(lesson.id, exIndex, results.current));
      else setSummary(await api.courseRound(lesson.id, exIndex, results.current));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your results.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lesson.id, lesson.kind, exIndex]);

  const finished = summary !== null || testResult !== null;
  useEffect(() => {
    if (pos >= queue.length && !finished) void finishRound();
  }, [pos, queue.length, finished, finishRound]);

  const startExercise = (index: number, roundNo: number, keepResults = false) => {
    if (!keepResults) results.current = [];
    lastFirst.current = null;
    setSummary(null);
    setExIndex(index);
    setRound(roundNo);
    setQueue(buildRound(lesson.exercises[index], roundNo, isTest));
    setPos(0);
    setPhase("prompt");
    setCheck(null);
    setPicked(null);
  };

  const continueAfterSummary = () => {
    if (testResult) return onDone(testResult.next_test ? { kind: "test", id: testResult.next_test } : testResult.next);
    if (!summary) return;
    if (summary.lesson_passed && exIndex + 1 >= lesson.exercises.length)
      return onDone(summary.next ?? (summary.next_lesson ? { kind: "lesson", id: summary.next_lesson } : null));
    startExercise(exIndex + 1, 0);
  };

  // Insert the correction procedure after a miss: repeat it, back up, and a delayed re-test.
  const correct = (missedResult: number | null) => {
    if (!step || step.kind === "partner" || isTest) return;
    const tag = missedResult ?? -1;
    const extra: Step[] = [];
    if (step.kind === "choose") {
      setQueue((q) => [
        ...q.slice(0, pos + 1 + DELAY),
        { kind: "choose", item: step.item, step: "delayed", correction: tag },
        ...q.slice(pos + 1 + DELAY),
      ]);
      return;
    }
    extra.push({
      kind: "lead",
      item: step.item,
      step: "retest",
      correction: tag,
    });
    if (ex.type !== "dialogue") {
      const earlier = queue
        .slice(0, pos)
        .filter(
          (s): s is Extract<Step, { kind: "test" }> =>
            s.kind === "test" && s.item !== step.item,
        )
        .slice(-BACK_UP)
        .map((s): Step => ({
          kind: "test",
          item: s.item,
          step: "practice",
          correction: tag,
        }));
      extra.push(...earlier);
    }
    const delayed: Step = {
      kind: "test",
      item: step.item,
      step: "delayed",
      correction: tag,
    };
    setQueue((q) => {
      const head = [...q.slice(0, pos + 1), ...extra];
      const rest = q.slice(pos + 1);
      return [...head, ...rest.slice(0, DELAY), delayed, ...rest.slice(DELAY)];
    });
  };

  /** "I said it right": count the last miss as correct and drop its correction steps. */
  const overrule = () => {
    const at = lastFirst.current;
    if (at === null) return;
    results.current[at] = {
      ...results.current[at],
      correct: true,
      override: true,
    };
    lastFirst.current = null;
    setQueue((q) =>
      q.filter(
        (s, i) => i <= pos || !("correction" in s) || s.correction !== at,
      ),
    );
    if (phase === "wrong") next();
  };

  const onAudio = useCallback(
    async (blob: Blob) => {
      if (!step || !item || (step.kind !== "test" && step.kind !== "lead"))
        return;
      setPhase("checking");
      let result: AnswerCheck;
      try {
        result = await api.courseCheck(
          item.src ?? [lesson.id, exIndex, step.item],
          item.key!,
          blob,
          isTest ? lesson.id : undefined,
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Checking failed.");
        setPhase("ready");
        return;
      }
      if (result.silent) {
        setSilentTries((n) => n + 1);
        setPhase("ready");
        return;
      }
      if (result.again && !unclear) {
        // Borderline: probably right, but not clear enough to count either way. Ask once more.
        setUnclear(true);
        setPhase("ready");
        if (listenFirst) void recorder.start();
        return;
      }
      setCheck(result);
      if (step.kind === "lead") {
        record({
          key: item.key!,
          step: step.step,
          correct: result.correct,
          score: result.score,
        });
        if (result.correct || leadTries >= 1) {
          setPhase("right");
        } else {
          setLeadTries((n) => n + 1);
          setPhase("wrong");
        }
        return;
      }
      const at = record({
        key: item.key!,
        step: step.step,
        correct: result.correct,
        score: result.score,
        card: step.step === "first" ? item.card : undefined,
      });
      if (result.correct) {
        setPhase("right");
      } else {
        if (step.step === "first") lastFirst.current = at;
        setPhase("wrong");
        correct(step.step === "first" ? at : null);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [step, item, lesson.id, exIndex, leadTries, pos, queue, isTest, unclear, listenFirst],
  );

  const recorder = useRecorder(onAudio);

  // Prompt: play what this step needs, then open the mic (hands-free) or wait.
  useEffect(() => {
    if (!step || !item || phase !== "prompt" || finished) return;
    let live = true;
    (async () => {
      if (step.kind === "partner") {
        await clip.play(api.ttsUrl(item.line!.text, "normal"));
        if (live) setTimeout(() => live && next(), 500);
        return;
      }
      if (step.step === "first") lastFirst.current = null; // "I said it right" only applies to the item just missed
      const toReady = (p: Phase) => (p === "prompt" ? "ready" : p); // the learner may already have answered
      if (step.kind === "choose") {
        // Listening items play first; written-form items ("___ дом") play the full sentence after answering.
        if (!item.prompt) await clip.play(api.ttsUrl(item.audio!.text, "normal"));
        if (live) setPhase(toReady);
        return;
      }
      // A correction's "say it after me" follows straight on from hearing the model, so it isn't replayed.
      if (step.kind === "lead" && step.step !== "retest")
        await clip.play(api.ttsUrl(item.answer!.text, "normal"));
      else if (step.kind === "test" && item.ask)
        await clip.play(api.ttsUrl(item.ask.text, "normal"));
      if (!live) return;
      setPhase(toReady);
      if (listenFirst) void recorder.start();
    })();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos, phase === "prompt", finished, queue.length]);

  useEffect(() => {
    if (recorder.recording) setPhase((p) => (p === "ready" ? "listening" : p));
  }, [recorder.recording]);

  // Re-open the mic after "didn't hear anything" (twice at most, then wait for the learner).
  useEffect(() => {
    if (
      phase === "ready" &&
      silentTries > 0 &&
      silentTries < 3 &&
      listenFirst &&
      step &&
      step.kind !== "choose"
    )
      void recorder.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [silentTries]);

  // After a verdict: move on, or model the right answer before the correction steps.
  useEffect(() => {
    if (!step) return;
    let timer: number | undefined;
    let live = true;
    if (phase === "right" && step.kind === "lead" && check && !check.correct && item)
      // "Say it after me" moves on after two misses: hear it once more first.
      void clip.play(api.ttsUrl(item.answer!.text, "normal")).then(() => {
        if (live) timer = window.setTimeout(next, ADVANCE_MS);
      });
    else if (phase === "right") timer = window.setTimeout(next, ADVANCE_MS);
    if (phase === "wrong" && isTest) timer = window.setTimeout(next, 2 * ADVANCE_MS); // a test doesn't teach
    else if (phase === "wrong" && item) {
      const text = step.kind === "choose" ? item.audio?.text : item.answer!.text;
      const slow = step.kind !== "choose" && farOff(check);
      const model = async () => {
        if (!text) return;
        if (slow) {
          await clip.play(api.ttsUrl(text, "slow"));
          if (live) await pause(400);
        }
        if (live) await clip.play(api.ttsUrl(text, "normal"));
      };
      void model().then(() => {
        if (!live) return;
        if (step.kind === "lead") {
          setCheck(null);
          setPhase("ready");
          if (listenFirst) void recorder.start();
        } else timer = window.setTimeout(next, slow ? FAR_OFF_HOLD_MS : 1200);
      });
    }
    if (phase === "chosen" && item?.prompt && item.audio)
      void clip.play(api.ttsUrl(item.audio.text, "normal")).then(() => {
        if (live) timer = window.setTimeout(next, ADVANCE_MS / 2);
      });
    else if (phase === "chosen") timer = window.setTimeout(next, ADVANCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  const choose = (option: number) => {
    if (
      !step ||
      step.kind !== "choose" ||
      !item ||
      (phase !== "ready" && phase !== "prompt")
    )
      return;
    clip.stop();
    setPicked(option);
    const ok = option === item.correct;
    const at = record({ key: item.key!, step: step.step, correct: ok });
    if (ok) setPhase("chosen");
    else {
      if (step.step === "first") lastFirst.current = at;
      setPhase("wrong");
      correct(null);
    }
  };

  const replay = () => {
    if (!step || !item) return;
    const text =
      step.kind === "partner"
        ? item.line!.text
        : step.kind === "choose"
          ? item.audio?.text
          : step.kind === "lead"
            ? item.answer!.text
            : item.ask?.text;
    if (text) void clip.play(api.ttsUrl(text, "normal"));
  };

  const toggleMic = () => {
    if (recorder.recording) recorder.stop();
    else if (
      step &&
      (step.kind === "test" || step.kind === "lead") &&
      (phase === "ready" || phase === "listening")
    ) {
      clip.stop();
      void recorder.start();
    }
  };

  useHotkeys((key) => {
    if (finished) {
      // Space takes the default: go again after a round below the mark, otherwise move on. Enter always moves on.
      if (key === "space" && summary && !summary.passed)
        return (startExercise(exIndex, round + 1), true);
      if (key === "space" || key === "enter") return (continueAfterSummary(), true);
      return false;
    }
    if (key === "space") return (toggleMic(), true);
    if (key === "r") return (replay(), true);
    if (key === "o" && lastFirst.current !== null) return (overrule(), true);
    if (key === "escape") return (setPaused((p) => !p), true);
    if (step?.kind === "choose" && /^[1-9]$/.test(key))
      return (choose(Number(key) - 1), true);
    return false;
  });

  const firsts = results.current.filter((r) => r.step === "first");
  const counted = isTest
    ? lesson.exercises.reduce((n, e) => n + e.items.length, 0)
    : buildRound(ex, round).filter(
        (s) => s.kind !== "partner" && s.step === "first",
      ).length;

  if (testResult) {
    const { passed, kind } = testResult;
    const percent = Math.round(testResult.accuracy * 100);
    const units = lesson.title.replace(/^Test: /, "");
    return (
      <div className="lesson-player">
        <div className="card player-card">
          <div className="player-summary">
            <div className={`summary-mark ${passed ? "good" : "close"}`}>
              {passed ? "✓" : "↻"}
            </div>
            <h2>
              {passed
                ? kind === "placement"
                  ? `You've tested out of ${units}`
                  : "Test passed!"
                : kind === "placement"
                  ? "Good to know where to start"
                  : "Not quite there yet"}
            </h2>
            <p>
              {percent}% right ({testResult.total - testResult.missed} of {testResult.total}
              {passed ? "" : `, ${PASS_PERCENT}% to pass`}).
            </p>
            <p>
              {passed
                ? testResult.next_test
                  ? "Want to try the next test too, or start the lessons from here?"
                  : testResult.next?.kind === "lesson"
                    ? `Lesson ${testResult.next.id} is unlocked.`
                    : "That's every lesson so far."
                : testResult.remedial
                  ? `The ${testResult.missed} item${testResult.missed === 1 ? "" : "s"} you missed will come back in review. ${testResult.next?.kind === "lesson" ? `Lesson ${testResult.next.id} is unlocked. ` : ""}A short fix-up lesson on them is there if you want it, and then you can retake the test.`
                  : testResult.next?.kind === "lesson"
                    ? `Start with lesson ${testResult.next.id}: those lessons will fill the gaps.`
                    : "Keep going with the lessons."}
            </p>
          </div>
        </div>
        <ActionBar
          left={<button onClick={onExit}>← Lessons</button>}
          center={
            <>
              {testResult.next_test && testResult.next?.kind === "lesson" && (
                <button onClick={() => onDone(testResult.next)}>
                  Start lesson {testResult.next.id}
                </button>
              )}
              {testResult.remedial && (
                <button onClick={() => onDone({ kind: "remedial", id: lesson.id })}>
                  Fix-up lesson
                </button>
              )}
              <button className="primary" onClick={continueAfterSummary}>
                {testResult.next_test
                  ? "Next test →"
                  : testResult.next?.kind === "lesson"
                      ? `Lesson ${testResult.next.id} →`
                      : "Finish"}
              </button>
            </>
          }
          hint="Space or Enter: continue"
        />
      </div>
    );
  }

  if (summary) {
    const lessonDone =
      summary.lesson_passed && exIndex + 1 >= lesson.exercises.length;
    return (
      <div className="lesson-player">
        <div className="card player-card">
          <div className="player-summary">
            <div
              className={`summary-mark ${summary.passed ? "good" : "close"}`}
            >
              {summary.passed ? "✓" : "↻"}
            </div>
            <h2>
              {lessonDone
                ? lesson.kind === "remedial"
                  ? "Fix-up done!"
                  : "Lesson done!"
                : summary.passed
                  ? `${ex.title}: passed`
                  : `${ex.title}: done`}
            </h2>
            <p>
              {Math.round(summary.accuracy * 100)}% right first time
              {summary.passed
                ? ""
                : ` (${PASS_PERCENT}% to pass). Go again now, or move on: the ones you missed will come back in review.`}
            </p>
            {lessonDone && (
              <p>
                {lesson.kind === "remedial"
                  ? "Now take the test again."
                  : summary.next?.kind === "test"
                    ? "That's the unit done. Next comes its test: one try at everything in the unit, then the next unit opens."
                    : summary.next_lesson
                      ? "The next lesson is unlocked."
                      : "That's every lesson so far."}
              </p>
            )}
          </div>
        </div>
        <ActionBar
          left={<button onClick={onExit}>← Lessons</button>}
          center={
            <>
              {!summary.passed && (
                <button className="primary" onClick={() => startExercise(exIndex, round + 1)}>
                  ↻ Go again
                </button>
              )}
              <button className={summary.passed ? "primary" : ""} onClick={continueAfterSummary}>
                {lessonDone
                  ? summary.next?.kind === "test"
                    ? "Take the test →"
                    : summary.next_lesson
                      ? "Next lesson →"
                      : "Finish"
                  : "Next exercise →"}
              </button>
            </>
          }
          hint={summary.passed ? "Space or Enter: continue" : "Space: go again · Enter: move on"}
        />
      </div>
    );
  }

  return (
    <div className="lesson-player">
      <header className="player-head">
        <div className="player-progress">
          {lesson.exercises.map((e, i) => (
            <span
              key={i}
              className={i < exIndex ? "done" : i === exIndex ? "now" : ""}
              title={e.title}
            />
          ))}
        </div>
        <div className="player-title">
          <strong>{ex.title}</strong>
          {round > 0 && <span className="pill close">firm-up {round}</span>}
          {isTest && <span className="pill">test</span>}
          <span className="muted">
            {isTest ? results.current.length : firsts.filter((r) => r.correct).length}/{counted}
          </span>
        </div>
        <p className={`player-instruction ${pos > 0 && !item?.question ? "muted" : ""}`}>
          {item?.question ?? ex.instruction}
        </p>
      </header>
      {error && <div className="banner error">{error}</div>}
      {recorder.error && <div className="banner error">{recorder.error}</div>}

      {step && item && (
        <div className={`card player-card ${phase}`} key={pos}>
          <StepView
            step={step}
            item={item}
            phase={phase}
            check={check}
            picked={picked}
            onChoose={choose}
            isTest={isTest}
          />
          {silentTries > 0 && phase === "ready" && (
            <p className="hint">I didn't hear anything. Say it again.</p>
          )}
          {unclear && silentTries === 0 && (phase === "ready" || phase === "listening") && (
            <p className="hint">I didn't catch that clearly. Say it again.</p>
          )}
        </div>
      )}

      <ActionBar
        level={recorder.recording ? recorder.level : undefined}
        left={<button onClick={onExit}>← Lessons</button>}
        center={
          step?.kind === "test" || step?.kind === "lead" ? (
            <>
              <button
                onClick={replay}
                disabled={step.kind === "test" && !item?.ask}
              >
                🔊 Again
              </button>
              <button
                className={recorder.recording ? "record on" : "record"}
                onClick={toggleMic}
                disabled={
                  recorder.processing ||
                  phase === "checking" ||
                  phase === "right" ||
                  phase === "prompt"
                }
              >
                {recorder.recording
                  ? "■ Stop"
                  : phase === "checking"
                    ? "Checking…"
                    : "🎙 Answer"}
              </button>
              {lastFirst.current !== null && phase === "wrong" && (
                <button
                  onClick={overrule}
                  title="The checker got it wrong: count it as right"
                >
                  ✓ I said it right
                </button>
              )}
            </>
          ) : step?.kind === "choose" ? (
            <button onClick={replay} disabled={!!item?.prompt && phase !== "chosen" && phase !== "wrong"}>
              🔊 Again
            </button>
          ) : null
        }
        right={
          <button
            className="toggle"
            aria-pressed={handsFree}
            onClick={() => setHandsFree(!handsFree)}
            title="Open the mic automatically"
          >
            Hands-free {handsFree ? "on" : "off"}
          </button>
        }
        hint={
          step?.kind === "choose"
            ? "1–4: choose · R: hear again"
            : "Space: answer / stop · R: hear again · O: I said it right · Esc: pause hands-free"
        }
      />
    </div>
  );
}

/** What's happening on this step, in a few words: the banner at the top of the card. */
function stepMode(
  step: Step,
  item: CourseItem,
  phase: Phase,
  check: AnswerCheck | null,
  isTest: boolean,
): { text: string; tone?: "good" | "bad" | "live" } {
  if (step.kind === "partner") return { text: "💬 Your friend says" };
  if (step.kind === "choose") {
    if (phase === "chosen") return { text: "✓ Right", tone: "good" };
    if (phase === "wrong") return { text: "✗ Not quite", tone: "bad" };
    return { text: item.prompt ? "✍️ Choose the word that fits" : "🔊 Listen. Which one did you hear?" };
  }
  if (phase === "checking") return { text: "Checking…" };
  if (phase === "right")
    return check?.correct ? { text: "✓ Right", tone: "good" } : { text: "Keep going →" };
  if (phase === "wrong" && isTest) return { text: "✗ Not quite. The answer was:", tone: "bad" };
  if (phase === "wrong")
    return { text: farOff(check) ? "✗ Not quite. Listen slowly, then again:" : "✗ Not quite. Listen:", tone: "bad" };
  if (phase === "listening") return { text: "🎙 Listening…", tone: "live" };
  if (step.kind === "lead")
    return { text: step.step === "retest" ? "🔁 Say it after me" : "👂 Listen, then say it after me" };
  return { text: item.ask ? "🎙 Your turn: answer in Russian" : "🎙 Your turn: say it in Russian" };
}

/** The Russian line is the largest thing on the card; whole sentences step down a size so they fit. */
const ruClass = (text: string) => `tier-ru ${text.length > 16 ? "long" : ""}`;

/** Why a spoken answer was marked wrong, when the coloured letters alone would not say. */
function missReason(check: AnswerCheck | null): string | null {
  if (!check || check.correct) return null;
  if (check.heard) return `That sounded like «${check.heard}».`;
  if (check.reason === "fit") return "The sounds were there, but it wasn't quite the answer: say exactly the words shown.";
  return null;
}

/**
 * One step of a lesson. What's shown follows one order of importance: the Russian (largest), then the
 * English, then the picture. Whether the Russian is shown depends on the step: it is the answer, so it's
 * hidden until the learner has answered, except when they're repeating after the voice.
 */
function StepView({
  step,
  item,
  phase,
  check,
  picked,
  onChoose,
  isTest,
}: {
  step: Step;
  item: CourseItem;
  phase: Phase;
  check: AnswerCheck | null;
  picked: number | null;
  onChoose: (i: number) => void;
  isTest: boolean;
}) {
  const mode = stepMode(step, item, phase, check, isTest);
  const banner = <div className={`step-mode ${mode.tone ?? ""}`}>{mode.text}</div>;
  const picture = item.cue ? <div className="tier-pic">{item.cue}</div> : null;

  if (step.kind === "partner")
    return (
      <div className="step partner">
        {banner}
        <div className={ruClass(item.line!.plain)} lang="ru">
          <Stressed text={item.line!.display} />
        </div>
        {item.english && <div className="tier-en">{item.english}</div>}
        {picture}
      </div>
    );

  if (step.kind === "choose") {
    const answered = phase === "chosen" || phase === "wrong";
    return (
      <div className="step choose">
        {banner}
        {item.prompt ? (
          <>
            <div className={ruClass(item.prompt.plain)} lang="ru">
              <Stressed text={answered && item.audio ? item.audio.display : item.prompt.display} />
            </div>
            {item.english && <div className="tier-en">{item.english}</div>}
            {picture}
          </>
        ) : (
          <div className={`${ruClass(item.audio!.plain)} ${answered ? "" : "placeholder"}`} lang="ru">
            {answered ? <Stressed text={item.audio!.display} /> : "🔊"}
          </div>
        )}
        <div className="choose-options">
          {item.options!.map((o, i) => (
            <button
              key={i}
              className={`choose-option ${answered && i === item.correct ? "good" : ""} ${answered && i === picked && i !== item.correct ? "bad" : ""}`}
              onClick={() => onChoose(i)}
              disabled={answered}
            >
              <span className="key">{i + 1}</span>
              <span className="option-main" lang={item.prompt ? "ru" : undefined}>
                {o}
              </span>
              {item.labels?.[i] && <span className="option-label">{item.labels[i]}</span>}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const showAnswer = step.kind === "lead" || phase === "right" || phase === "wrong";
  const reason = phase === "wrong" && step.kind === "test" ? missReason(check) : null;
  return (
    <div className="step say">
      {banner}
      {item.ask && (
        <div className="ask" lang="ru">
          🗣 <Stressed text={item.ask.display} />
        </div>
      )}
      {showAnswer ? (
        <div className={ruClass(item.answer!.plain)} lang="ru">
          {check && check.words.length ? (
            check.words.map((w, i) => (
              <span key={i} className="word">
                <Letters letters={w.letters} />{" "}
              </span>
            ))
          ) : (
            <Stressed text={item.answer!.display} />
          )}
        </div>
      ) : (
        <div className={`tier-ru placeholder ${phase === "listening" ? "live" : ""}`} aria-label="your answer">
          {phase === "listening" ? "🎙 …" : "?"}
        </div>
      )}
      {item.english && <div className="tier-en">{item.english}</div>}
      {picture}
      {reason && <div className="verdict bad">{reason}</div>}
    </div>
  );
}
