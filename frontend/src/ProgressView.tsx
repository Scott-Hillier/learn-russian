import { useEffect, useMemo, useState, type ComponentProps } from "react";
import { api, type PairGroup, type ProgressSummary } from "./api";
import { ActivityChart, LetterHeatmap, ScoreChart } from "./charts";
import Layout from "./Layout";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;

const ALPHABET = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя".split("");
const SOURCE_LABELS: Record<string, string> = {
  letter: "Letter drills",
  reading: "Reading",
  phrase: "Phrases",
  custom: "Sentence words & chunks",
  sentence: "Full sentences",
  flashcard: "Flashcards",
  pair: "Sound pairs",
};

export default function ProgressView({ layout }: { layout: LayoutProps }) {
  const [data, setData] = useState<ProgressSummary | null>(null);
  const [pairs, setPairs] = useState<PairGroup[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.progressSummary().then(setData).catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
    api.minimalPairs().then(setPairs).catch(() => {});
  }, []);

  const pairGroupFor = useMemo(() => {
    const map = new Map<string, PairGroup>();
    for (const g of pairs) for (const l of g.letters) if (!map.has(l)) map.set(l, g);
    return map;
  }, [pairs]);

  const sidebar = (
    <p className="sidebar-note">
      Everything here is computed from your practice history, stored only on this Mac in
      backend/userdata/progress.db.
    </p>
  );

  if (!data) {
    return (
      <Layout {...layout} sidebar={sidebar}>
        {error ? <div className="banner error">{error}</div> : <div className="card">Loading…</div>}
      </Layout>
    );
  }

  const { totals, flashcards } = data;
  const practisedLetters = Object.keys(data.letters).length;
  const empty = totals.attempts === 0 && totals.reviews === 0;

  return (
    <Layout {...layout} sidebar={sidebar}>
      <div className="dashboard">
        <header className="lesson-head">
          <h2>Your progress</h2>
          {empty && <p>Nothing here yet. Practise a few letters or phrases and come back!</p>}
        </header>

        <div className="stat-grid">
          <div className="stat hero">
            <span>Day streak</span>
            <strong>{totals.streak_days}</strong>
            <small>{totals.active_days} active days in total</small>
          </div>
          <div className="stat">
            <span>Speaking attempts</span>
            <strong>{totals.attempts.toLocaleString()}</strong>
          </div>
          <div className="stat">
            <span>Average score</span>
            <strong>{totals.average_score === null ? "—" : `${totals.average_score}%`}</strong>
          </div>
          <div className="stat">
            <span>Flashcards learned</span>
            <strong>{flashcards.learned.toLocaleString()}</strong>
            <small>
              {flashcards.learning} learning · {flashcards.new} new
            </small>
          </div>
          <div className="stat">
            <span>Letters practised</span>
            <strong>
              {practisedLetters} <small>/ 33</small>
            </strong>
          </div>
        </div>

        <ActivityChart days={data.daily} />
        <ScoreChart days={data.daily} />

        <details className="table-view">
          <summary>Show daily numbers as a table</summary>
          <div className="card-table-wrap">
            <table className="card-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Speaking attempts</th>
                  <th>Flashcard reviews</th>
                  <th>Average score</th>
                </tr>
              </thead>
              <tbody>
                {[...data.daily].reverse().map((d) => (
                  <tr key={d.date}>
                    <td>{d.date}</td>
                    <td>{d.attempts}</td>
                    <td>{d.reviews}</td>
                    <td>{d.average_score === null ? "—" : `${d.average_score}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>

        <div className="dash-row">
          <LetterHeatmap letters={ALPHABET} stats={data.letters} />
          <section className="viz problem-sounds">
            <strong>Sounds to work on</strong>
            {data.problem_letters.length === 0 ? (
              <p className="muted">
                {practisedLetters === 0
                  ? "Practise some words first. Letters you find hard will show up here."
                  : "No weak sounds right now (every letter with 3+ attempts averages 85% or more). 🎉"}
              </p>
            ) : (
              <ul>
                {data.problem_letters.map((p) => {
                  const group = pairGroupFor.get(p.letter);
                  return (
                    <li key={p.letter}>
                      <span className="problem-letter" lang="ru">
                        {p.letter}
                      </span>
                      <span className="problem-meter" aria-hidden>
                        <span style={{ width: `${Math.round(p.average * 100)}%` }} />
                      </span>
                      <span>
                        <b>{Math.round(p.average * 100)}%</b> <span className="muted">over {p.count}</span>
                      </span>
                      <button className="link" onClick={() => layout.onMode(group ? "pairs" : "alphabet")}>
                        {group ? `Practise ${group.title}` : "Letter lessons"}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            {Object.keys(data.by_source).length > 0 && (
              <>
                <strong className="sub">Where you've practised</strong>
                <ul className="source-list">
                  {Object.entries(data.by_source)
                    .sort((a, b) => b[1] - a[1])
                    .map(([source, count]) => (
                      <li key={source}>
                        <span>{SOURCE_LABELS[source] ?? source}</span>
                        <b>{count}</b>
                      </li>
                    ))}
                </ul>
              </>
            )}
          </section>
        </div>
      </div>
    </Layout>
  );
}
