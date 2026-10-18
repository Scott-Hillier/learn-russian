import { useCallback, useEffect, useState, type ComponentProps } from "react";
import ActionBar from "./ActionBar";
import { api, type CourseLesson, type CourseOverview, type CourseTrack } from "./api";
import Layout from "./Layout";
import LessonPlayer from "./LessonPlayer";
import { useHotkeys } from "./useHotkeys";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;

const TRACK_LABELS: Record<CourseTrack, string> = {
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

export default function CourseView({ layout }: { layout: LayoutProps }) {
  const [overview, setOverview] = useState<CourseOverview | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [lesson, setLesson] = useState<CourseLesson | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      api
        .course()
        .then((o) => {
          setOverview(o);
          setSelected((id) => id ?? o.current ?? o.lessons[0]?.id ?? null);
        })
        .catch(() => setError("Can't reach the backend. Is ./start.sh running?")),
    [],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const summary = overview?.lessons.find((l) => l.id === selected) ?? null;

  useEffect(() => {
    setLesson(null);
    if (!summary || summary.status === "locked") return;
    api
      .courseLesson(summary.id)
      .then(setLesson)
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the lesson."));
  }, [summary?.id, summary?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    if (!lesson) return;
    if (lesson.status === "passed" && lesson.exercise >= lesson.exercises.length) {
      await api.courseRestart(lesson.id);
      setLesson({ ...lesson, exercise: 0 });
    }
    setPlaying(true);
  };

  useHotkeys((key) => {
    if (!playing && key === "enter" && lesson) return void start(), true;
    return false;
  });

  const sidebar = (
    <>
      <p className="sidebar-note">
        One lesson at a time. Pass every exercise to unlock the next lesson. Everything else is in the Practice
        screens above.
      </p>
      <ul className="lesson-list">
        {overview?.lessons.map((l) => (
          <li key={l.id}>
            <button
              className={`${l.id === selected ? "active" : ""} ${l.status}`}
              onClick={() => {
                setPlaying(false);
                setSelected(l.id);
              }}
            >
              <span className="sentence-row">
                <span>
                  {STATUS_ICON[l.status]} {l.id}. <span lang="ru">{l.title}</span>
                </span>
              </span>
              <small>{l.goal}</small>
            </button>
          </li>
        ))}
      </ul>
    </>
  );

  if (playing && lesson)
    return (
      <Layout {...layout} sidebar={sidebar}>
        <LessonPlayer
          key={lesson.id}
          lesson={lesson}
          onExit={() => {
            setPlaying(false);
            void refresh();
            void api.courseLesson(lesson.id).then(setLesson);
          }}
          onLessonPassed={(nextId) => {
            setPlaying(false);
            void refresh().then(() => setSelected(nextId ?? lesson.id));
          }}
        />
      </Layout>
    );

  const done = lesson ? Math.min(lesson.exercise, lesson.exercises.length) : 0;
  return (
    <Layout {...layout} sidebar={sidebar}>
      {error && <div className="banner error">{error}</div>}
      {summary && (
        <div className="lesson course-lesson">
          <header className="lesson-head">
            <h2>
              Lesson {summary.id}: <span lang="ru">{summary.title}</span>
            </h2>
            <p>{summary.goal}</p>
          </header>
          {summary.status === "locked" ? (
            <div className="card">
              🔒 Pass lesson {summary.id - 1} to unlock this one. Lessons build on each other, so each one starts once
              the last is solid.
            </div>
          ) : (
            lesson && (
              <>
                <ol className="exercise-list">
                  {lesson.exercises.map((e, i) => (
                    <li key={i} className={i < done || lesson.status === "passed" ? "done" : i === done ? "now" : ""}>
                      <span className="exercise-mark">{i < done || lesson.status === "passed" ? "✓" : i + 1}</span>
                      <span className="exercise-title">{e.title}</span>
                      <span className="muted">{TRACK_LABELS[e.track]}</span>
                    </li>
                  ))}
                </ol>
                <p className="muted small-print">
                  Each exercise needs {Math.round((overview?.pass_accuracy ?? 0.9) * 100)}% right first time. If it
                  isn't there yet, you get the same exercise again in a new order until it is.
                </p>
              </>
            )
          )}
        </div>
      )}
      {lesson && summary?.status !== "locked" && (
        <ActionBar
          center={
            <button className="primary" onClick={() => void start()}>
              {lesson.status === "passed" ? "Practise again" : done > 0 ? "Continue lesson →" : "Start lesson →"}
            </button>
          }
          hint="Enter: start · Hands-free: the mic opens by itself after each question"
        />
      )}
    </Layout>
  );
}
