import { useCallback, useEffect, useRef, useState } from "react";
import ActionBar from "./ActionBar";
import { api, type AttemptResult, type FlashCard, type Group, type RatingName, type Remaining, type StudyNext } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";
import { useHotkeys } from "./useHotkeys";
import { useRecorder } from "./useRecorder";
import { Letters } from "./WordFeedback";

interface Props {
  deckId: number | null;
  deckName: string;
  /** Review the Learned words deck (shuffled, as often as you like) instead of learning the next group. */
  learned?: boolean;
  onReviewed: () => void;
  onExit: () => void;
  onReviewLearned?: () => void;
}

/** The card on screen: either the scheduler's pick or one from a pass through the Learned words deck. */
type Current = NonNullable<StudyNext["next"]> | { card: FlashCard; kind: "learned"; left: number };

function shuffle<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
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

export default function StudySession({ deckId, deckName, learned, onReviewed, onExit, onReviewLearned }: Props) {
  const [next, setNext] = useState<Current | null | undefined>(undefined);
  const [revealed, setRevealed] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [myAudio, setMyAudio] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState({ count: 0, again: 0, scores: [] as number[] });
  const audio = useAudio(setError);
  const queue = useRef<FlashCard[] | null>(null);
  // Learning: the group this session started in, and how many of its new words have been learned so far.
  const [group, setGroup] = useState<Group | null>(null);
  const [introduced, setIntroduced] = useState(0);
  const [remaining, setRemaining] = useState<Remaining | null>(null);

  const load = useCallback(async (group: Group | null, introduced: number) => {
    try {
      let current: Current | null;
      if (learned) {
        if (!queue.current) queue.current = shuffle(await api.learnedCards());
        const card = queue.current.shift();
        current = card ? { card, kind: "learned", left: queue.current.length } : null;
      } else {
        const r = await api.studyNext(deckId, group ? group.left - introduced : null);
        if (!group) setGroup(r.remaining.group);
        setRemaining(r.remaining);
        current = r.next;
      }
      setNext(current);
      setRevealed(current?.kind === "new");
      setResult(null);
      setMyAudio((old) => {
        if (old) URL.revokeObjectURL(old);
        return null;
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }, [deckId, learned]);

  useEffect(() => {
    load(null, 0);
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
  // Also covers the recorder finishing its file, before `checking` is set — see useRecorder.
  const scoring = checking || rec.processing;

  const toggleRecord = useCallback(() => {
    if (rec.recording) rec.stop();
    else if (!scoring && card) {
      audio.stop();
      rec.start();
    }
  }, [rec, scoring, card, audio]);

  const rate = useCallback(
    async (rating: 1 | 2 | 3 | 4) => {
      if (!card || busy) return;
      setBusy(true);
      try {
        await api.rate(card.id, rating, result?.score ?? null, learned);
        // Reviewing learned words, "Again" sends the card back to the end of the pass for another go.
        if (learned && rating === 1) queue.current?.push(card);
        setSummary((s) => ({
          count: s.count + 1,
          again: s.again + (rating === 1 ? 1 : 0),
          scores: result ? [...s.scores, result.score] : s.scores,
        }));
        const nowIntroduced = introduced + (next?.kind === "new" ? 1 : 0);
        setIntroduced(nowIntroduced);
        onReviewed();
        await load(group, nowIntroduced);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [card, busy, result, learned, next, introduced, group, onReviewed, load],
  );

  /** Start over: the next group when learning, another shuffled pass when reviewing learned words. */
  const restart = useCallback(() => {
    queue.current = null;
    setSummary({ count: 0, again: 0, scores: [] });
    setGroup(null);
    setIntroduced(0);
    setNext(undefined);
    load(null, 0);
  }, [load]);

  const moreToLearn = !learned && (remaining?.new_total ?? 0) > 0;

  const listen = useCallback(
    (speed: "normal" | "slow") => card && audio.play(api.ttsUrl(card.text, speed)),
    [card, audio],
  );

  const suggested = result ? suggestRating(result.score) : null;

  useHotkeys((key) => {
    if (next === null && key === "enter") (moreToLearn ? restart : onExit)();
    else if (next === null && key === "r" && learned) restart();
    else if (next === null && key === "r" && onReviewLearned) onReviewLearned();
    else if (next === null && key === "escape") onExit();
    else if (!card) return false;
    else if (key === "space") toggleRecord();
    else if (rec.recording) return false;
    else if (key === "enter" && !revealed) setRevealed(true);
    else if (key === "enter") rate(suggested ?? 3);
    else if (revealed && ["1", "2", "3", "4"].includes(key)) rate(Number(key) as 1 | 2 | 3 | 4);
    else if (revealed && key === "l") listen("normal");
    else if (revealed && key === "s") listen("slow");
    else if (key === "p" && myAudio) audio.play(myAudio);
    else return false;
    return true;
  });

  if (next === undefined) return <div className="card">Loading…</div>;

  if (next === null) {
    const avg = summary.scores.length
      ? Math.round(summary.scores.reduce((a, b) => a + b, 0) / summary.scores.length)
      : null;
    const scoreLine = avg !== null && (
      <>
        {" "}
        with an average pronunciation score of <strong>{avg}%</strong>
      </>
    );
    const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

    if (learned) {
      return (
        <div className="card study-done">
          <h2>{summary.count ? "Review complete 🎉" : "No learned words yet"}</h2>
          {summary.count ? (
            <p>
              You reviewed <strong>{plural(summary.count, "card")}</strong>
              {scoreLine}. Go again whenever you like: reviewing learned words never changes their schedule.
            </p>
          ) : (
            <p>Finish a group of new words and they'll appear in your Learned words deck.</p>
          )}
          <ActionBar
            right={
              <>
                {summary.count > 0 && <button onClick={restart}>↻ Go again</button>}
                <button className="primary" onClick={onExit}>
                  Back to decks
                </button>
              </>
            }
            hint={
              <>
                <kbd>Enter</kbd> back{summary.count > 0 && <> · <kbd>R</kbd> go again</>}
              </>
            }
          />
        </div>
      );
    }

    const finishedGroup = group && introduced > 0 && introduced >= group.left;
    return (
      <div className="card study-done">
        <h2>
          {finishedGroup
            ? `Group ${group.number} complete 🎉`
            : summary.count
              ? "Session complete 🎉"
              : "Every word learned 🎉"}
        </h2>
        {summary.count > 0 ? (
          <p>
            {introduced > 0 ? (
              <>
                You learned <strong>{plural(introduced, "new word")}</strong>
                {summary.count > introduced && ` (${summary.count} cards in all)`}
              </>
            ) : (
              <>
                You did <strong>{plural(summary.count, "review")}</strong>
              </>
            )}
            {scoreLine}. Your Learned words deck now has <strong>{plural(remaining?.learned_words ?? 0, "word")}</strong>.
          </p>
        ) : (
          <p>There are no new words left here. Review your learned words any time.</p>
        )}
        <ActionBar
          right={
            <>
              {onReviewLearned && (remaining?.learned_words ?? 0) > 0 && (
                <button onClick={onReviewLearned}>Review learned words</button>
              )}
              {moreToLearn ? (
                <>
                  <button onClick={onExit}>Back to decks</button>
                  <button className="primary" onClick={restart}>
                    Next group →
                  </button>
                </>
              ) : (
                <button className="primary" onClick={onExit}>
                  Back to decks
                </button>
              )}
            </>
          }
          hint={
            <>
              <kbd>Enter</kbd> {moreToLearn ? "next group" : "back"}
              {onReviewLearned && (remaining?.learned_words ?? 0) > 0 && <> · <kbd>R</kbd> review learned words</>}
            </>
          }
        />
      </div>
    );
  }

  const isNew = next.kind === "new";
  const isLearned = next.kind === "learned";

  return (
    <div className="study">
      <div className="study-bar">
        <button className="link" onClick={onExit}>
          ← {deckName}
        </button>
        <span className="muted">
          {next.kind === "learned" ? (
            <>
              Learned words · {next.left} left · {summary.count} done
            </>
          ) : (
            <>
              Group {group?.number ?? next.remaining.group.number} ·{" "}
              {Math.min((group?.left ?? next.remaining.new) - introduced, next.remaining.new_total)} new ·{" "}
              {next.remaining.due} due · {summary.count} done
            </>
          )}
        </span>
      </div>

      <div className="card study-card">
        <div className="card-top">
          <span className={`state-badge ${isLearned ? "practice" : isNew ? "new" : card!.state}`}>
            {isLearned ? "Learned word" : isNew ? "New word" : "Review"}
          </span>
          {card!.tag && <span className="category">{card!.tag}</span>}
        </div>

        {!revealed ? (
          <>
            <div className="prompt-label">How do you say this in Russian?</div>
            <div className="prompt-english">{card!.english}</div>
            {card!.notes && <div className="muted">{card!.notes}</div>}
            <ActionBar
              level={rec.level}
              center={
                <>
                  <button className={`record ${rec.recording ? "on" : ""}`} onClick={toggleRecord} disabled={scoring}>
                    {rec.recording ? "■ Stop" : scoring ? "Checking…" : "🎙 Say it"}
                  </button>
                  <button onClick={() => setRevealed(true)}>Show answer</button>
                </>
              }
              hint={
                <>
                  Say it out loud from memory (<kbd>Space</kbd>), or <kbd>Enter</kbd> to show the answer if you don't
                  remember.
                </>
              }
            />
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
              <button className={`record ${rec.recording ? "on" : ""}`} onClick={toggleRecord} disabled={scoring}>
                {rec.recording ? "■ Stop" : scoring ? "Checking…" : result ? "🎙 Try again" : "🎙 Say it"}
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

            {isLearned ? (
              <ActionBar
                level={rec.level}
                hint={
                  <>
                    Doesn't change the schedule. <kbd>1</kbd> again · <kbd>Enter</kbd> next ·{" "}
                    <kbd>Space</kbd> record · <kbd>L</kbd> listen
                  </>
                }
              >
                <div className="ratings">
                  <button className="rating again" onClick={() => rate(1)} disabled={busy}>
                    <span>
                      <kbd>1</kbd> Again
                    </span>
                    <small>later in this review</small>
                  </button>
                  <button className="rating good" onClick={() => rate(3)} disabled={busy}>
                    <span>
                      <kbd>↵</kbd> Next card
                    </span>
                    <small>{next.left} left</small>
                  </button>
                </div>
              </ActionBar>
            ) : (
            <ActionBar
              level={rec.level}
              hint={
                suggested ? (
                  <>
                    Suggested from your pronunciation: <strong>{RATINGS[suggested - 1].label}</strong> (
                    <kbd>Enter</kbd>). Pick another if you didn't actually remember it.
                  </>
                ) : (
                  <>
                    <kbd>1</kbd>–<kbd>4</kbd> rate · <kbd>Enter</kbd> good · <kbd>Space</kbd> record · <kbd>L</kbd>{" "}
                    listen
                  </>
                )
              }
            >
              <div className="ratings">
                {RATINGS.map((r) => (
                  <button
                    key={r.value}
                    className={`rating ${r.name}${suggested === r.value ? " suggested" : ""}`}
                    onClick={() => rate(r.value)}
                    disabled={busy}
                  >
                    <span>
                      <kbd>{r.value}</kbd> {r.label}
                    </span>
                    <small>{next.intervals[r.name]}</small>
                  </button>
                ))}
              </div>
            </ActionBar>
            )}
          </>
        )}

        {(rec.error || error) && <div className="banner error">{rec.error || error}</div>}
      </div>
    </div>
  );
}
