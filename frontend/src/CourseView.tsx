import { useCallback, useEffect, useState, type ComponentProps } from "react";
import ActionBar from "./ActionBar";
import {
  api,
  type CourseKind,
  type CourseLesson,
  type CourseNext,
  type CourseOverview,
  type CourseTrack,
  type TestStatus,
} from "./api";
import Layout from "./Layout";
import LessonPlayer from "./LessonPlayer";
import { useHotkeys } from "./useHotkeys";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;

export const TRACK_LABELS: Record<CourseTrack, string> = {
  script: "🔤 Letters",
  frames: "🧩 Sentences",
  vocab: "🆕 Words",
  listening: "👂 Listening",
  sounds: "🎯 Sounds",
  numbers: "🔢 Numbers",
  dialogue: "💬 Dialogue",
  review: "🔁 Review",
};

const STATUS_ICON = { passed: "✅", available: "▶", locked: "🔒" } as const;
const TEST_ICON: Record<TestStatus, string> = {
  passed: "✅",
  available: "📝",
  remedial: "🔧",
  skip: "⏭",
  locked: "🔒",
};

/** What's selected on the course page: a lesson, or a unit's test (its fix-up lesson shows under the test). */
type Selection = { kind: "lesson" | "test"; id: number };

const same = (a: Selection | null, b: Selection) => a?.kind === b.kind && a.id === b.id;

export default function CourseView({
  layout,
  start,
  onStarted,
}: {
  layout: LayoutProps;
  /** Open this straight away (from the home screen). */
  start?: CourseNext | null;
  onStarted?: () => void;
}) {
  const [overview, setOverview] = useState<CourseOverview | null>(null);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [lesson, setLesson] = useState<CourseLesson | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const refresh = useCallback(
    () =>
      api
        .course()
        .then((o) => {
          setOverview(o);
          setSelected((s) => s ?? toSelection(o.next) ?? { kind: "lesson", id: o.lessons[0]?.id ?? 1 });
          return o;
        })
        .catch(() => {
          setError("Can't reach the backend. Is ./start.sh running?");
          return null;
        }),
    [],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const lessonSummary =
    selected?.kind === "lesson" ? (overview?.lessons.find((l) => l.id === selected.id) ?? null) : null;
  const testSummary = selected?.kind === "test" ? (overview?.tests.find((t) => t.unit === selected.id) ?? null) : null;
  const kind: CourseKind | null = lessonSummary
    ? "lesson"
    : testSummary
      ? testSummary.status === "remedial"
        ? "remedial"
        : "test"
      : null;
  const status = lessonSummary?.status ?? testSummary?.status;

  // Load what's selected (unless it's locked).
  useEffect(() => {
    setLesson(null);
    if (!selected || !kind || status === "locked") return;
    const load =
      kind === "lesson"
        ? api.courseLesson(selected.id)
        : kind === "remedial"
          ? api.courseRemedial(selected.id)
          : api.courseTest(selected.id);
    load.then(setLesson).catch((e) => setError(e instanceof Error ? e.message : "Couldn't load it."));
  }, [selected?.kind, selected?.id, kind, status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Coming from the home screen: open the next step and start it.
  useEffect(() => {
    if (!start) return;
    setSelected(toSelection(start));
    onStarted?.();
  }, [start]); // eslint-disable-line react-hooks/exhaustive-deps
  const [autoStart, setAutoStart] = useState(!!start);
  useEffect(() => {
    if (autoStart && lesson) {
      setAutoStart(false);
      void begin();
    }
  }, [autoStart, lesson]); // eslint-disable-line react-hooks/exhaustive-deps

  const begin = async () => {
    if (!lesson) return;
    if (lesson.kind === "lesson" && lesson.status === "passed" && lesson.exercise >= lesson.exercises.length) {
      await api.courseRestart(lesson.id);
      setLesson({ ...lesson, exercise: 0 });
    }
    setPlaying(true);
  };

  useHotkeys((key) => {
    if (!playing && key === "enter" && lesson) return void begin(), true;
    return false;
  });

  const sidebar = (
    <>
      <p className="sidebar-note">
        One lesson at a time. Finish every exercise to unlock the next lesson; every {overview?.unit_size ?? 5} lessons
        a short test shows what's solid. Everything else is in the Practice screens above.
      </p>
      <ul className="lesson-list">
        {overview?.lessons.map((l) => {
          const test = overview.tests.find((t) => t.last === l.id);
          return (
            <li key={l.id}>
              <button
                className={`${same(selected, { kind: "lesson", id: l.id }) ? "active" : ""} ${l.status}`}
                onClick={() => {
                  setPlaying(false);
                  setSelected({ kind: "lesson", id: l.id });
                }}
              >
                <span className="sentence-row">
                  <span>
                    {STATUS_ICON[l.status]} {l.id}. <span lang="ru">{l.title}</span>
                  </span>
                </span>
                <small>{l.goal}</small>
              </button>
              {test && (
                <button
                  className={`test-entry ${same(selected, { kind: "test", id: test.unit }) ? "active" : ""} ${test.status}`}
                  onClick={() => {
                    setPlaying(false);
                    setSelected({ kind: "test", id: test.unit });
                  }}
                >
                  <span>
                    {TEST_ICON[test.status]} Test: lessons {test.first}–{test.last}
                  </span>
                  <small>
                    {test.status === "passed"
                      ? `Passed${test.best !== null ? ` (${Math.round(test.best * 100)}%)` : ""}`
                      : test.status === "remedial"
                        ? "Optional: fix-up lesson, then retake"
                        : test.status === "skip"
                          ? "Already know these? Test out"
                          : test.status === "available"
                            ? test.taken
                              ? "Retake the test any time"
                              : "Unit done: take the test"
                            : "Finish the unit first"}
                  </small>
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );

  const onDone = (next: CourseNext | null) => {
    setPlaying(false);
    void refresh().then((o) => {
      if (!o) return;
      const target = toSelection(next) ?? selected;
      setSelected(target ? { ...target } : null);
    });
  };

  if (playing && lesson)
    return (
      <Layout {...layout} sidebar={sidebar}>
        <LessonPlayer
          key={`${lesson.kind}-${lesson.id}-${lesson.attempt ?? 0}`}
          lesson={lesson}
          onExit={() => {
            setPlaying(false);
            void refresh();
            setSelected((s) => (s ? { ...s } : s)); // reload what was being played
          }}
          onDone={onDone}
        />
      </Layout>
    );

  const done = lesson ? Math.min(lesson.exercise, lesson.exercises.length) : 0;
  const firstTime = overview && !overview.started;
  return (
    <Layout {...layout} sidebar={sidebar}>
      {error && <div className="banner error">{error}</div>}
      {firstTime && lessonSummary?.id === 1 && (
        <div className="card placement-card">
          <strong>Already know some Russian?</strong> Take the placement test for lessons 1–
          {overview.unit_size} instead. Pass it and you start further on; otherwise you start here with nothing lost.{" "}
          <button onClick={() => setSelected({ kind: "test", id: 1 })}>Take the placement test</button>
        </div>
      )}
      {lessonSummary && (
        <div className="lesson course-lesson">
          <header className="lesson-head">
            <h2>
              Lesson {lessonSummary.id}: <span lang="ru">{lessonSummary.title}</span>
            </h2>
            <p>{lessonSummary.goal}</p>
            {lessonSummary.placed && <p className="muted">You tested out of this lesson. You can still go through it.</p>}
          </header>
          {lessonSummary.status === "locked" ? (
            <div className="card">
              🔒{" "}
              {lessonSummary.id > 1 && (lessonSummary.id - 1) % (overview?.unit_size ?? 5) === 0
                ? `Take the test for lessons ${lessonSummary.id - (overview?.unit_size ?? 5)}–${lessonSummary.id - 1} to unlock this one.`
                : `Finish lesson ${lessonSummary.id - 1} to unlock this one.`}{" "}
              Lessons build on each other, so they open in order.
            </div>
          ) : (
            lesson && <ExerciseList lesson={lesson} done={done} passAccuracy={overview?.pass_accuracy ?? 0.9} />
          )}
        </div>
      )}
      {testSummary && (
        <div className="lesson course-lesson">
          <header className="lesson-head">
            <h2>
              {testSummary.status === "remedial" ? "Fix-up" : "Test"}: lessons {testSummary.first}–{testSummary.last}
            </h2>
            <p>
              {testSummary.status === "remedial"
                ? "Optional: go over what the test showed wasn't solid yet, then take the test again. The next unit is already open."
                : testSummary.status === "skip"
                  ? `Already know lessons ${testSummary.first}–${testSummary.last}? Pass this test (${Math.round((overview?.test_pass_accuracy ?? 0.9) * 100)}%) to skip them. If you don't, nothing is lost: you just start the lessons.`
                  : `One try at a sample of everything in lessons ${testSummary.first}–${testSummary.last}, with no help. Taking it unlocks the next unit; ${Math.round((overview?.test_pass_accuracy ?? 0.9) * 100)}% passes it.`}
            </p>
            {testSummary.attempts > 0 && (
              <p className="muted">
                Tries so far: {testSummary.attempts}
                {testSummary.best !== null && ` · best ${Math.round(testSummary.best * 100)}%`}
              </p>
            )}
          </header>
          {testSummary.status === "locked" ? (
            <div className="card">🔒 Pass the units before this one first.</div>
          ) : (
            lesson &&
            (lesson.kind === "remedial" ? (
              <ExerciseList lesson={lesson} done={done} passAccuracy={overview?.pass_accuracy ?? 0.9} />
            ) : (
              <p className="muted">
                {lesson.exercises.map((e) => `${e.items.length} ${e.title.toLowerCase()}`).join(" · ")} items. About{" "}
                {Math.max(3, Math.round(lesson.exercises.reduce((n, e) => n + e.items.length, 0) / 4))} minutes.
              </p>
            ))
          )}
        </div>
      )}
      {lesson && status !== "locked" && (
        <ActionBar
          center={
            <button className="primary" onClick={() => void begin()}>
              {lesson.kind === "test"
                ? testSummary?.status === "skip"
                  ? "Take the test →"
                  : testSummary?.status === "passed"
                    ? "Take it again"
                    : "Start the test →"
                : lesson.kind === "remedial"
                  ? done > 0
                    ? "Continue fix-up →"
                    : "Start fix-up →"
                  : lesson.status === "passed"
                    ? "Practise again"
                    : done > 0
                      ? "Continue lesson →"
                      : "Start lesson →"}
            </button>
          }
          hint="Enter: start · Hands-free: the mic opens by itself after each question"
        />
      )}
    </Layout>
  );
}

function toSelection(next: CourseNext | null | undefined): Selection | null {
  return next ? { kind: next.kind === "lesson" ? "lesson" : "test", id: next.id } : null;
}

function ExerciseList({ lesson, done, passAccuracy }: { lesson: CourseLesson; done: number; passAccuracy: number }) {
  const passed = lesson.kind === "lesson" && lesson.status === "passed";
  return (
    <>
      <ol className="exercise-list">
        {lesson.exercises.map((e, i) => (
          <li key={i} className={i < done || passed ? "done" : i === done ? "now" : ""}>
            <span className="exercise-mark">{i < done || passed ? "✓" : i + 1}</span>
            <span className="exercise-title">{e.title}</span>
            <span className="muted">{TRACK_LABELS[e.track]}</span>
          </li>
        ))}
      </ol>
      <p className="muted small-print">
        {Math.round(passAccuracy * 100)}% right first time passes an exercise. Below that you can go again or move on:
        whatever you miss comes back in review.
      </p>
    </>
  );
}
