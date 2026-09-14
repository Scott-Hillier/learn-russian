import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AttemptResult, type AttemptSource, type Phrase, type Timing } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";
import { useRecorder } from "./useRecorder";
import { Letters, WordDetail } from "./WordFeedback";

interface Props {
  phrase: Phrase;
  source: AttemptSource;
  onPrev?: () => void;
  onNext?: () => void;
  /** Letters being practised: their scores are highlighted in the result. */
  focus?: string[];
  /** Reading challenge: hide transliteration and pronunciation hints until revealed or attempted. */
  hideHints?: boolean;
  /** e.g. "3 / 12", shown in the card header. */
  position?: string;
  /** Compare speaking pace with the native voice. */
  timing?: boolean;
  onResult?: (result: AttemptResult) => void;
}

export default function PracticeCard({
  phrase,
  source,
  onPrev,
  onNext,
  focus,
  hideHints,
  position,
  timing,
  onResult,
}: Props) {
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [myAudioUrl, setMyAudioUrl] = useState<string | null>(null);
  const [best, setBest] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(!hideHints);
  const audio = useAudio(setError);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  const listenTo = useCallback((text: string, speed: "normal" | "slow") => audio.play(api.ttsUrl(text, speed)), [audio]);
  const listen = useCallback((speed: "normal" | "slow") => listenTo(phrase.text, speed), [phrase.text, listenTo]);

  const onRecorded = useCallback(
    async (blob: Blob) => {
      setMyAudioUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
      setChecking(true);
      setError(null);
      try {
        const r = await api.attempt(phrase.text, blob, source, timing);
        setResult(r);
        setRevealed(true);
        setBest((b) => Math.max(b ?? 0, r.score));
        const worst = r.words.reduce((w, cur, i) => (cur.score < r.words[w].score ? i : w), 0);
        setSelected(r.words.length && r.words[worst].status !== "good" ? worst : null);
        onResultRef.current?.(r);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setChecking(false);
      }
    },
    [phrase.text, source, timing],
  );

  const rec = useRecorder(onRecorded);

  const toggleRecord = useCallback(() => {
    if (rec.recording) rec.stop();
    else if (!checking) {
      audio.stop();
      setResult(null);
      rec.start();
    }
  }, [rec, checking, audio]);

  // Keyboard shortcuts (ignored while typing in an input).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.code === "Space") {
        e.preventDefault();
        toggleRecord();
      } else if (e.key === "l") listen("normal");
      else if (e.key === "s") listen("slow");
      else if (e.key === "ArrowRight") onNext?.();
      else if (e.key === "ArrowLeft") onPrev?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleRecord, listen, onNext, onPrev]);

  const statusWord = (score: number) =>
    score >= 85 ? "Excellent!" : score >= 55 ? "Good. Almost there" : score >= 30 ? "Keep going" : "Let's try again";

  const focusScores = result && focus ? focusLetterScores(result, focus) : [];

  return (
    <div className="card">
      <div className="card-top">
        <span className="category">
          {phrase.category}
          {position && <> · {position}</>}
        </span>
        {best !== null && <span className="best">Best: {best}%</span>}
      </div>

      <div className="target" lang="ru">
        {result ? (
          result.words.map((w, i) => (
            <button
              key={i}
              className={`word ${w.status}${selected === i ? " selected" : ""}`}
              onClick={() => setSelected(selected === i ? null : i)}
              title="Show details for this word"
            >
              <Letters letters={w.letters} />
            </button>
          ))
        ) : (
          <Stressed text={phrase.display} />
        )}
      </div>
      {revealed ? (
        <>
          <div className="translit">{phrase.translit}</div>
          {phrase.sounds_like && (
            <div className="sounds-like">
              sounds like <strong>{phrase.sounds_like}</strong>
            </div>
          )}
          {phrase.english && <div className="english">“{phrase.english}”</div>}
          {phrase.note && <div className="note">💡 {phrase.note}</div>}
        </>
      ) : (
        <div className="reading-challenge">
          Read it yourself, then say it.{" "}
          <button className="link" onClick={() => setRevealed(true)}>
            Show hint
          </button>
        </div>
      )}

      <div className="controls">
        <button onClick={() => listen("normal")} title="Listen (L)">
          🔊 Listen
        </button>
        <button onClick={() => listen("slow")} title="Listen slowly (S)">
          🐢 Slow
        </button>
        <button
          className={`record ${rec.recording ? "on" : ""}`}
          onClick={toggleRecord}
          disabled={checking}
          title="Record (Space)"
        >
          {rec.recording ? "■ Stop" : checking ? "Checking…" : "🎙 Say it"}
        </button>
      </div>

      <div className="meter" aria-hidden>
        <div style={{ width: `${rec.level * 100}%` }} />
      </div>
      {rec.recording && <div className="hint">Listening… stops automatically when you pause.</div>}
      {(rec.error || error) && <div className="banner error">{rec.error || error}</div>}

      {result && (
        <div className="result">
          <div className="score-row">
            <div className={`score ${result.score >= 85 ? "good" : result.score >= 55 ? "close" : "wrong"}`}>
              {result.score}%
            </div>
            <div>
              <strong>{statusWord(result.score)}</strong>
              <div className="heard">
                I heard: <span lang="ru">{result.heard || "(nothing)"}</span>
              </div>
              {result.timing && <TimingNote timing={result.timing} />}
              {focusScores.length > 0 && (
                <div className="focus-scores">
                  {focusScores.map(({ letter, score }) => (
                    <span key={letter} className={`pill ${score >= 0.85 ? "good" : score >= 0.55 ? "close" : "wrong"}`}>
                      <span lang="ru">{letter}</span> {Math.round(score * 100)}%
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="legend">
            <span className="letter good">clear</span>
            <span className="letter close">almost</span>
            <span className="letter wrong">needs work</span>
            <span className="letter silent">silent</span>
            <span className="muted">· click a word for details</span>
          </div>
          {selected !== null && result.words[selected] && (
            <WordDetail word={result.words[selected]} onListen={listenTo} />
          )}
          <ul className="tips">
            {result.tips.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
          <div className="controls small">
            {myAudioUrl && <button onClick={() => audio.play(myAudioUrl)}>▶ My recording</button>}
            <button onClick={() => listen("normal")}>▶ Native</button>
            {onNext && <button onClick={onNext}>Next →</button>}
          </div>
        </div>
      )}

      {(onPrev || onNext) && (
        <div className="nav">
          <button onClick={onPrev} disabled={!onPrev}>
            ← Previous
          </button>
          <button onClick={onNext} disabled={!onNext}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

export function TimingNote({ timing }: { timing: Timing }) {
  const { ratio } = timing;
  const verdict =
    ratio > 1.5
      ? "much slower than native. That's fine while learning; speed up as it gets comfortable"
      : ratio > 1.2
        ? "a little slower than native"
        : ratio >= 0.8
          ? "close to native pace 👍"
          : "faster than native. Slow down a little so every sound is clear";
  return (
    <div className="timing-note">
      ⏱ {timing.yours.toFixed(1)}s vs native {timing.native.toFixed(1)}s: {verdict}.
    </div>
  );
}

/** Average score of each focus letter (case-insensitive) across the attempt. */
function focusLetterScores(result: AttemptResult, focus: string[]) {
  return focus
    .map((letter) => {
      const scores = result.words
        .flatMap((w) => w.letters)
        .filter((l) => l.char.toLowerCase() === letter.toLowerCase() && l.score !== null)
        .map((l) => l.score as number);
      return { letter: letter.toLowerCase(), score: scores.length ? scores.reduce((a, b) => a + b) / scores.length : -1 };
    })
    .filter((s) => s.score >= 0);
}
