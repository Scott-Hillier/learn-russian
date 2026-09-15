import { useCallback, useEffect, useMemo, useState, type ComponentProps } from "react";
import ActionBar from "./ActionBar";
import { api, type PairGroup, type PairWord, type Phrase } from "./api";
import Drill, { type DrillItem } from "./Drill";
import Layout from "./Layout";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";
import { useHotkeys } from "./useHotkeys";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;
type Tab = "listen" | "say";

export default function PairsView({ layout }: { layout: LayoutProps }) {
  const [groups, setGroups] = useState<PairGroup[]>([]);
  const [groupId, setGroupId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("listen");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    return api
      .minimalPairs()
      .then((g) => {
        setGroups(g);
        setGroupId((id) => id ?? g[0]?.id ?? null);
      })
      .catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const group = groups.find((g) => g.id === groupId) ?? null;

  const sidebar = (
    <>
      <p className="sidebar-note">
        Pairs of words that differ by one sound. Groups for sounds you've scored lowest on are listed first.
      </p>
      <ul className="lesson-list">
        {groups.map((g) => (
          <li key={g.id}>
            <button
              className={g.id === groupId ? "active" : ""}
              onClick={() => {
                setGroupId(g.id);
                setTab("listen");
              }}
            >
              <span className="sentence-row">
                <span lang="ru">{g.title}</span>
                {g.recommended && <span className="pill close">practise</span>}
              </span>
              <small>
                {g.your_average === null ? "not practised yet" : `your score: ${Math.round(g.your_average * 100)}%`}
              </small>
            </button>
          </li>
        ))}
      </ul>
    </>
  );

  return (
    <Layout {...layout} sidebar={sidebar}>
      {error && <div className="banner error">{error}</div>}
      {group && (
        <div className="lesson" key={group.id}>
          <header className="lesson-head">
            <h2 lang="ru">{group.title}</h2>
            <p>{group.explanation}</p>
            <div className="tabs">
              <button className={tab === "listen" ? "active" : ""} onClick={() => setTab("listen")}>
                👂 Listen & choose
              </button>
              <button className={tab === "say" ? "active" : ""} onClick={() => setTab("say")}>
                🎙 Say the pairs
              </button>
            </div>
          </header>
          {tab === "listen" && <ListenQuiz key={`quiz-${group.id}`} group={group} onSay={() => setTab("say")} />}
          {tab === "say" && (
            <Drill
              key={`say-${group.id}`}
              items={sayItems(group)}
              source="pair"
              onResult={() => void refresh()}
              banner={
                group.pairs.some((p) => !p.speak) ? (
                  <div className="drill-banner">
                    Some pairs here are listening-only: the scorer can't reliably hear that difference yet.
                  </div>
                ) : null
              }
            />
          )}
          <h3 className="section-label">All pairs in this group (click to hear)</h3>
          <PairTable group={group} />
        </div>
      )}
    </Layout>
  );
}

function toPhrase(word: PairWord, category: string): Phrase {
  return { ...word, id: 0, category };
}

function sayItems(group: PairGroup): DrillItem[] {
  return group.pairs
    .filter((p) => p.speak)
    .flatMap((p) =>
      [p.a, p.b].map((w) => ({
        phrase: toPhrase(w, `${p.a.plain} / ${p.b.plain}`),
        focus: group.letters.filter((l) => w.plain.toLowerCase().includes(l)),
      })),
    );
}

function PairTable({ group }: { group: PairGroup }) {
  const audio = useAudio();
  return (
    <div className="pair-table">
      {group.pairs.map((p, i) => (
        <div key={i} className="pair-row">
          {[p.a, p.b].map((w, j) => (
            <button key={j} className="pair-word" onClick={() => audio.play(api.ttsUrl(w.text, "normal"))}>
              🔊 <span className="pair-ru">
                <Highlight word={w} letters={group.letters} />
              </span>
              <span className="muted">{w.english}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

function Highlight({ word, letters }: { word: PairWord; letters: string[] }) {
  // Highlight the letters this group contrasts, keeping stress accents intact.
  const out: { s: string; hit: boolean }[] = [];
  const text = word.display;
  for (let i = 0; i < text.length; i++) {
    let ch = text[i];
    if (text[i + 1] === "́") ch += text[++i];
    out.push({ s: ch, hit: letters.includes(ch[0].toLowerCase()) });
  }
  return (
    <span lang="ru" className="ru">
      {out.map((p, i) => (p.hit ? <mark key={i}>{p.s}</mark> : <Stressed key={i} text={p.s} />))}
    </span>
  );
}

const ROUNDS = 10;

function ListenQuiz({ group, onSay }: { group: PairGroup; onSay: () => void }) {
  const rounds = useMemo(
    () =>
      Array.from({ length: ROUNDS }, () => {
        const pair = group.pairs[Math.floor(Math.random() * group.pairs.length)];
        const answer = Math.random() < 0.5 ? "a" : "b";
        return { pair, answer } as const;
      }),
    [group],
  );
  const [index, setIndex] = useState(-1); // -1: not started (audio needs a click first)
  const [chosen, setChosen] = useState<"a" | "b" | null>(null);
  const [correct, setCorrect] = useState(0);
  const audio = useAudio();

  const round = rounds[index];
  const playRound = (i: number) => {
    const r = rounds[i];
    if (r) audio.play(api.ttsUrl(r.pair[r.answer].text, "normal"));
  };

  const begin = (i: number) => {
    setIndex(i);
    setChosen(null);
    playRound(i);
  };

  const restart = () => {
    setCorrect(0);
    begin(0);
  };

  const choose = (side: "a" | "b") => {
    if (!round || chosen) return;
    setChosen(side);
    if (side === round.answer) setCorrect((c) => c + 1);
  };

  useHotkeys((key) => {
    if (index === -1) {
      if (key !== "enter" && key !== "space") return false;
      begin(0);
    } else if (index >= ROUNDS) {
      if (key === "enter") onSay();
      else if (key === "r") restart();
      else return false;
    } else if (!chosen && (key === "1" || key === "2")) choose(key === "1" ? "a" : "b");
    else if (key === "r" || key === "l" || (!chosen && key === "space")) playRound(index);
    else if (chosen && (key === "enter" || key === "space" || key === "arrowright")) begin(index + 1);
    else return false;
    return true;
  });

  if (index === -1) {
    return (
      <div className="card quiz">
        <p className="quiz-prompt">You'll hear one word from a pair. Pick the word you heard.</p>
        <ActionBar
          center={
            <button className="record" onClick={() => begin(0)}>
              ▶ Start ({ROUNDS} rounds)
            </button>
          }
          hint={
            <>
              <kbd>Enter</kbd> start
            </>
          }
        />
      </div>
    );
  }

  if (index >= ROUNDS) {
    return (
      <div className="card quiz">
        <h2>
          {correct} / {ROUNDS} correct
        </h2>
        <p>
          {correct >= 9
            ? "Your ear can hear this difference. Now practise saying it."
            : "These sounds take time to hear apart. Try another round."}
        </p>
        <ActionBar
          center={<button onClick={restart}>↻ Again</button>}
          right={
            <button className="primary" onClick={onSay}>
              🎙 Say the pairs →
            </button>
          }
          hint={
            <>
              <kbd>Enter</kbd> say the pairs · <kbd>R</kbd> another round
            </>
          }
        />
      </div>
    );
  }

  return (
    <div className="card quiz">
      <div className="card-top">
        <span className="category">
          Round {index + 1} / {ROUNDS}
        </span>
        <span className="best">Score: {correct}</span>
      </div>
      <p className="quiz-prompt">Which word did you hear?</p>
      <div className="quiz-options pair-options">
        {(["a", "b"] as const).map((side, i) => {
          const w = round.pair[side];
          const state = !chosen ? "" : side === round.answer ? "right" : side === chosen ? "wrong" : "dim";
          return (
            <button key={side} className={`quiz-option ${state}`} onClick={() => choose(side)} disabled={!!chosen}>
              <span lang="ru" className="pair-ru">
                <kbd>{i + 1}</kbd> <Stressed text={w.display} />
              </span>
              <small className="muted">{w.english}</small>
            </button>
          );
        })}
      </div>
      {chosen && (
        <div className={`quiz-feedback ${chosen === round.answer ? "right" : "wrong"}`}>
          <strong>{chosen === round.answer ? "Correct!" : `It was “${round.pair[round.answer].plain}”.`}</strong>
          <div className="controls small">
            <button onClick={() => audio.play(api.ttsUrl(round.pair.a.text, "slow"))}>🔊 {round.pair.a.plain}</button>
            <button onClick={() => audio.play(api.ttsUrl(round.pair.b.text, "slow"))}>🔊 {round.pair.b.plain}</button>
          </div>
        </div>
      )}
      <ActionBar
        center={
          <button onClick={() => playRound(index)} title="Play again (R)">
            🔊 Play again
          </button>
        }
        right={
          <button className={chosen ? "primary" : ""} onClick={() => begin(index + 1)} disabled={!chosen} title="Next (Enter)">
            {index === ROUNDS - 1 ? "See score →" : "Next →"}
          </button>
        }
        hint={
          chosen ? (
            <>
              <kbd>Enter</kbd> next · <kbd>R</kbd> play again
            </>
          ) : (
            <>
              <kbd>1</kbd> / <kbd>2</kbd> choose · <kbd>R</kbd> play again
            </>
          )
        }
      />
    </div>
  );
}
