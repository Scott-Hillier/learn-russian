import { useCallback, useEffect, useState } from "react";
import { api, type AttemptResult, type RatingName, type StudyNext } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";
import { useRecorder } from "./useRecorder";
import { Letters } from "./WordFeedback";

interface Props {
  deckId: number | null;
  deckName: string;
  onReviewed: () => void;
  onExit: () => void;
}

const RATINGS: { value: 1 | 2 | 3 | 4; name: RatingName; label: string }[] = [
  { value: 1, name: "again", label: "Again" },
  { value: 2, name: "hard", label: "Hard" },
  { value: 3, name: "good", label: "Good" },
  { value: 4, name: "easy", label: "Easy" },
];

/** Suggest a rating from the pronunciation score of a from-memory attempt. */
function suggestRating(score: number): 1 | 2 | 3 {
  return score >= 85 ? 3 : score >= 55 ? 2 : 1;
}

export default function StudySession({ deckId, deckName, onReviewed, onExit }: Props) {
  const [next, setNext] = useState<StudyNext["next"] | undefined>(undefined);
  const [revealed, setRevealed] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [myAudio, setMyAudio] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState({ count: 0, again: 0, scores: [] as number[] });
  const audio = useAudio(setError);

  const load = useCallback(async () => {
    try {
      const r = await api.studyNext(deckId);
      setNext(r.next);
      setRevealed(r.next?.kind === "new");
      setResult(null);
      setMyAudio((old) => {
        if (old) URL.revokeObjectURL(old);
        return null;
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }, [deckId]);

  useEffect(() => {
    load();
  }, [load]);

  const card = next?.card;

  const onRecorded = useCallback(
    async (blob: Blob) => {
      if (!card) return;
      setMyAudio((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
      setChecking(true);
      setError(null);
      try {
        setResult(await api.attempt(card.text, blob, "flashcard"));
        setRevealed(true);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setChecking(false);
      }
    },
    [card],
  );
  const rec = useRecorder(onRecorded);

  const toggleRecord = useCallback(() => {
    if (rec.recording) rec.stop();
    else if (!checking && card) {
      audio.stop();
      rec.start();
    }
  }, [rec, checking, card, audio]);

  const rate = useCallback(
    async (rating: 1 | 2 | 3 | 4) => {
      if (!card || busy) return;
      setBusy(true);
      try {
        await api.rate(card.id, rating, result?.score ?? null);
        setSummary((s) => ({
          count: s.count + 1,
          again: s.again + (rating === 1 ? 1 : 0),
          scores: result ? [...s.scores, result.score] : s.scores,
        }));
        onReviewed();
        await load();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [card, busy, result, onReviewed, load],
  );

  const listen = useCallback(
    (speed: "normal" | "slow") => card && audio.play(api.ttsUrl(card.text, speed)),
    [card, audio],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT" || !card) return;
      if (e.code === "Space") {
        e.preventDefault();
        toggleRecord();
      } else if (e.key === "Enter" && !revealed) {
        setRevealed(true);
      } else if (revealed && ["1", "2", "3", "4"].includes(e.key)) {
        rate(Number(e.key) as 1 | 2 | 3 | 4);
      } else if (revealed && e.key === "l") listen("normal");
      else if (revealed && e.key === "s") listen("slow");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, revealed, toggleRecord, rate, listen]);

  if (next === undefined) return <div className="card">Loading…</div>;

  if (next === null) {
    const avg = summary.scores.length
      ? Math.round(summary.scores.reduce((a, b) => a + b, 0) / summary.scores.length)
      : null;
    return (
      <div className="card study-done">
        <h2>{summary.count ? "Session complete 🎉" : "Nothing to study right now"}</h2>
        {summary.count > 0 ? (
          <p>
            You reviewed <strong>{summary.count}</strong> card{summary.count === 1 ? "" : "s"}
            {avg !== null && (
              <>
                {" "}
                with an average pronunciation score of <strong>{avg}%</strong>
              </>
            )}
            . {summary.again > 0 && `${summary.again} will come back again soon.`}
          </p>
        ) : (
          <p>All due cards are done and today's new cards have been introduced. Come back later!</p>
        )}
        <div className="controls">
          <button className="record" onClick={onExit}>
            Back
          </button>
        </div>
      </div>
    );
  }

  const suggested = result ? suggestRating(result.score) : null;
  const isNew = next.kind === "new";

  return (
    <div className="study">
      <div className="study-bar">
        <button className="link" onClick={onExit}>
          ← {deckName}
        </button>
        <span className="muted">
          {next.remaining.due} due · {next.remaining.new} new · {summary.count} done
        </span>
      </div>

      <div className="card study-card">
        <div className="card-top">
          <span className={`state-badge ${isNew ? "new" : card!.state}`}>{isNew ? "New word" : "Review"}</span>
          {card!.tag && <span className="category">{card!.tag}</span>}
        </div>

        {!revealed ? (
          <>
            <div className="prompt-label">How do you say this in Russian?</div>
            <div className="prompt-english">{card!.english}</div>
            {card!.notes && <div className="muted">{card!.notes}</div>}
            <div className="controls">
              <button className={`record ${rec.recording ? "on" : ""}`} onClick={toggleRecord} disabled={checking}>
                {rec.recording ? "■ Stop" : checking ? "Checking…" : "🎙 Say it"}
              </button>
              <button onClick={() => setRevealed(true)}>Show answer</button>
            </div>
            <div className="hint">
              Say it out loud from memory (<kbd>Space</kbd>), or <kbd>Enter</kbd> to reveal if you don't remember.
            </div>
          </>
        ) : (
          <>
            {isNew && <div className="prompt-label">Listen, say it a few times, then rate how well you know it.</div>}
            {!isNew && <div className="prompt-english small">{card!.english}</div>}
            <div className="target" lang="ru">
              {result ? (
                result.words.map((w, i) => (
                  <span key={i} className={`word ${w.status}`}>
                    <Letters letters={w.letters} />
                  </span>
                ))
              ) : (
                <Stressed text={card!.display} />
              )}
            </div>
            <div className="translit">{card!.translit}</div>
            {isNew && <div className="english">“{card!.english}”</div>}
            {card!.notes && <div className="note">💡 {card!.notes}</div>}

            <div className="controls">
              <button onClick={() => listen("normal")}>🔊 Listen</button>
              <button onClick={() => listen("slow")}>🐢 Slow</button>
              <button className={`record ${rec.recording ? "on" : ""}`} onClick={toggleRecord} disabled={checking}>
                {rec.recording ? "■ Stop" : checking ? "Checking…" : result ? "🎙 Try again" : "🎙 Say it"}
              </button>
              {myAudio && <button onClick={() => audio.play(myAudio)}>▶ Mine</button>}
            </div>

            {result && (
              <div className="study-result">
                <span className={`pill ${result.score >= 85 ? "good" : result.score >= 55 ? "close" : "wrong"}`}>
                  {result.score}%
                </span>
                <span className="muted">
                  I heard: <span lang="ru">{result.heard || "(nothing)"}</span>
                </span>
                {result.tips[0] && result.score < 85 && <div className="study-tip">{result.tips[0]}</div>}
              </div>
            )}

            <div className="ratings">
              {RATINGS.map((r) => (
                <button
                  key={r.value}
                  className={`rating ${r.name}${suggested === r.value ? " suggested" : ""}`}
                  onClick={() => rate(r.value)}
                  disabled={busy}
                >
                  <kbd>{r.value}</kbd> {r.label}
                  <small>{next.intervals[r.name]}</small>
                </button>
              ))}
            </div>
            {suggested && (
              <div className="hint">
                Suggested from your pronunciation: <strong>{RATINGS[suggested - 1].label}</strong>. Pick a different
                one if you didn't actually remember it.
              </div>
            )}
          </>
        )}

        <div className="meter" aria-hidden>
          <div style={{ width: `${rec.level * 100}%` }} />
        </div>
        {(rec.error || error) && <div className="banner error">{rec.error || error}</div>}
      </div>
    </div>
  );
}
