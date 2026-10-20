import { useEffect, useState, type ComponentProps } from "react";
import ActionBar from "./ActionBar";
import { api, type CourseNext, type CourseOverview, type CourseStats, type StudyStats } from "./api";
import { TRACK_LABELS } from "./CourseView";
import Layout from "./Layout";
import Stressed from "./Stressed";
import { useHotkeys } from "./useHotkeys";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;

/** Today: the next step on the lesson path, plus how the course is going. */
export default function HomeView({ layout, onStart }: { layout: LayoutProps; onStart: (next: CourseNext) => void }) {
  const [overview, setOverview] = useState<CourseOverview | null>(null);
  const [stats, setStats] = useState<CourseStats | null>(null);
  const [cards, setCards] = useState<StudyStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .course()
      .then(setOverview)
      .catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
    api.courseStats().then(setStats).catch(() => {});
    api.studyStats().then(setCards).catch(() => {});
  }, []);

  const next = overview?.next ?? null;
  useHotkeys((key) => {
    if (key === "enter" && next) return (onStart(next), true);
    return false;
  });

  const sidebar = (
    <p className="sidebar-note">
      Your daily lesson is the main route. Each one takes about 20 minutes. The Practice screens below are there
      whenever you want extra review.
    </p>
  );

  if (!overview)
    return (
      <Layout {...layout} sidebar={sidebar}>
        {error ? <div className="banner error">{error}</div> : <div className="card">Loading…</div>}
      </Layout>
    );

  const passed = overview.lessons.filter((l) => l.status === "passed").length;
  const nextLesson = next?.kind === "lesson" ? overview.lessons.find((l) => l.id === next.id) : null;
  const nextTest = next && next.kind !== "lesson" ? overview.tests.find((t) => t.unit === next.id) : null;
  const units = overview.tests.length
    ? overview.tests
    : [{ unit: 1, first: 1, last: overview.lessons.length, status: "locked" as const }];
  const extra = overview.lessons.filter((l) => !overview.tests.some((t) => l.id >= t.first && l.id <= t.last));

  return (
    <Layout {...layout} sidebar={sidebar}>
      <div className="dashboard home">
        <header className="lesson-head">
          <h2>Today</h2>
          <p>
            {passed} of {overview.lessons.length} lessons passed
            {stats && stats.first_tries > 0 && ` · ${stats.items_seen} things practised`}
          </p>
        </header>

        <section className="card next-step">
          {nextLesson ? (
            <>
              <span className="muted">{nextLesson.exercise > 0 ? "Carry on with" : "Next up"}</span>
              <h3>
                Lesson {nextLesson.id}: <span lang="ru">{nextLesson.title}</span>
              </h3>
              <p>{nextLesson.goal}</p>
              {nextLesson.exercise > 0 && (
                <p className="muted">
                  {nextLesson.exercise} of {nextLesson.exercises} exercises done.
                </p>
              )}
            </>
          ) : nextTest ? (
            <>
              <span className="muted">Unit finished</span>
              <h3>
                Test: lessons {nextTest.first}–{nextTest.last}
              </h3>
              <p>One try at a sample of the unit, with no help. Taking it unlocks the next unit.</p>
            </>
          ) : (
            <>
              <h3>You've done every lesson so far 🎉</h3>
              <p>Keep everything fresh in the Practice screens: Flashcards, Sentences and Conversation.</p>
            </>
          )}
          {!overview.started && (
            <p className="muted">
              Already know some Russian?{" "}
              <button className="link" onClick={() => onStart({ kind: "test", id: 1 })}>
                Take the placement test
              </button>{" "}
              to start further on.
            </p>
          )}
        </section>

        {cards && cards.due > 0 && (
          <section className="card due-words">
            🃏 <b>{cards.due}</b> flashcard{cards.due === 1 ? " is" : "s are"} due. Words from your lessons also come
            back in each lesson's review.{" "}
            <button className="link" onClick={() => layout.onMode("flashcards")}>
              Review them now
            </button>
          </section>
        )}

        <section className="viz">
          <strong>Your path</strong>
          <ol className="path">
            {units.map((t) => (
              <li key={t.unit} className="path-unit">
                <span className="muted">
                  Lessons {t.first}–{t.last}
                </span>
                <span className="path-steps">
                  {overview.lessons
                    .filter((l) => l.id >= t.first && l.id <= t.last)
                    .map((l) => (
                      <span
                        key={l.id}
                        className={`path-step ${l.status} ${next?.kind === "lesson" && next.id === l.id ? "next" : ""}`}
                        title={`${l.id}. ${l.title}${l.placed ? " (tested out)" : ""}`}
                      >
                        {l.id}
                      </span>
                    ))}
                  {overview.tests.some((x) => x.unit === t.unit) && (
                    <span
                      className={`path-step test ${t.status} ${next && next.kind !== "lesson" && next.id === t.unit ? "next" : ""}`}
                      title={`Test: lessons ${t.first}–${t.last}`}
                    >
                      {t.status === "passed" ? "✓" : "📝"}
                    </span>
                  )}
                </span>
              </li>
            ))}
            {extra.length > 0 && overview.tests.length > 0 && (
              <li className="path-unit">
                <span className="muted">
                  Lessons {extra[0].id}–{extra[extra.length - 1].id}
                </span>
                <span className="path-steps">
                  {extra.map((l) => (
                    <span key={l.id} className={`path-step ${l.status}`} title={`${l.id}. ${l.title}`}>
                      {l.id}
                    </span>
                  ))}
                </span>
              </li>
            )}
          </ol>
        </section>

        {stats && stats.first_tries > 0 && (
          <div className="dash-row">
            <section className="viz">
              <strong>Right first time, by track</strong>
              <ul className="track-bars">
                {stats.tracks.map((t) => (
                  <li key={t.track}>
                    <span>{TRACK_LABELS[t.track]}</span>
                    <span className="problem-meter" aria-hidden>
                      <span style={{ width: `${Math.round(t.recent_accuracy * 100)}%` }} />
                    </span>
                    <span>
                      <b>{Math.round(t.recent_accuracy * 100)}%</b>{" "}
                      <span className="muted">
                        of {t.tries}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="muted small-print">Over each track's last 50 first tries (and test answers).</p>
            </section>
            <section className="viz">
              <strong>To work on</strong>
              {stats.work_on.length === 0 ? (
                <p className="muted">Nothing you've missed lately. 🎉</p>
              ) : (
                <ul className="work-on">
                  {stats.work_on.map((w) => (
                    <li key={w.key}>
                      <span className="cue">{w.cue}</span>
                      <span lang="ru">
                        <Stressed text={w.display} />
                      </span>
                      <span className="muted">{w.english}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="muted small-print">These come back first in your next lesson's review.</p>
              {stats.tests.length > 0 && (
                <>
                  <strong className="sub">Tests</strong>
                  <ul className="source-list">
                    {stats.tests.map((t, i) => {
                      const unit = overview.tests.find((x) => x.unit === t.unit);
                      return (
                        <li key={i}>
                          <span>
                            {t.passed ? "✅" : "↻"} Lessons {unit?.first}–{unit?.last}
                            {t.kind === "placement" ? " (placement)" : ""}
                          </span>
                          <b>{Math.round(t.accuracy * 100)}%</b>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </section>
          </div>
        )}
      </div>
      {next && (
        <ActionBar
          center={
            <button className="primary" onClick={() => onStart(next)}>
              {next.kind === "lesson"
                ? nextLesson && nextLesson.exercise > 0
                  ? `Continue lesson ${next.id} →`
                  : `Start lesson ${next.id} →`
                : "Take the test →"}
            </button>
          }
          hint="Enter: start"
        />
      )}
    </Layout>
  );
}
