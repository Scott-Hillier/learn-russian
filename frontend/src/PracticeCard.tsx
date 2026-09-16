import { useCallback, useEffect, useRef, useState } from "react";
import ActionBar, { AutoPlayToggle } from "./ActionBar";
import { api, type AttemptResult, type AttemptSource, type Phrase, type Timing } from "./api";
import { usePref } from "./prefs";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";
import { useHotkeys } from "./useHotkeys";
import { useRecorder } from "./useRecorder";
import { IntonationChart } from "./charts";
import { Letters, WordDetail } from "./WordFeedback";

interface Props {
  phrase: Phrase;
  source: AttemptSource;
  onPrev?: () => void;
  onNext?: () => void;
  /** Label of the next button, e.g. "Next: quiz →". */
  nextLabel?: string;
  /** Letters being practised: their scores are highlighted in the result. */
  focus?: string[];
  /** Reading challenge: hide transliteration and pronunciation hints until revealed or attempted. */
  hideHints?: boolean;
  /** e.g. "3 / 12", shown in the card header. */
  position?: string;
  /** Compare speaking pace with the native voice. */
  timing?: boolean;
  /** Show the pitch contour against the native voice. */
  intonation?: boolean;
  onResult?: (result: AttemptResult) => void;
}

export default function PracticeCard({
  phrase,
  source,
  onPrev,
  onNext,
  nextLabel = "Next →",
  focus,
  hideHints,
  position,
  timing,
  intonation,
  onResult,
}: Props) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [autoPlay] = usePref("autoplay", true);
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
        const r = await api.attempt(phrase.text, blob, source, timing, intonation);
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
    [phrase.text, source, timing, intonation],
  );

  const rec = useRecorder(onRecorded);
  // Covers the whole wait: stopping the recorder, then scoring. `checking` alone leaves a visible
  // gap while MediaRecorder finishes writing the audio.
  const busy = checking || rec.processing;

  const toggleRecord = useCallback(() => {
    if (rec.recording) rec.stop();
    else if (!busy) {
      audio.stop();
      setResult(null);
      rec.start();
    }
  }, [rec, busy, audio]);

  // Each item mounts a fresh card: bring it back into view and play it, unless it's a reading challenge.
  useEffect(() => {
    if (cardRef.current && cardRef.current.getBoundingClientRect().top < 0) window.scrollTo({ top: 0 });
    if (autoPlay && !hideHints) audio.play(api.ttsUrl(phrase.text, "normal"), { quiet: true });
    // Only on mount: toggling auto-play shouldn't replay the current item.
  }, []);

  useHotkeys((key) => {
    if (key === "space") toggleRecord();
    else if (key === "l") listen("normal");
    else if (key === "s") listen("slow");
    else if (key === "p" && myAudioUrl) audio.play(myAudioUrl);
    else if (rec.recording && key === "enter") rec.stop();
    else if (rec.recording) return false;
    else if ((key === "enter" || key === "arrowright") && onNext) onNext();
    else if (key === "arrowleft" && onPrev) onPrev();
    else return false;
    return true;
  });

  const statusWord = (score: number) =>
    score >= 85 ? "Excellent!" : score >= 55 ? "Good. Almost there" : score >= 30 ? "Keep going" : "Let's try again";

  const focusScores = result && focus ? focusLetterScores(result, focus) : [];

  return (
    <div className="card" ref={cardRef}>
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
          {phrase.translit && <div className="translit">{phrase.translit}</div>}
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

      {(rec.error || error) && <div className="banner error">{rec.error || error}</div>}
      {busy && <div className="hint">Checking your pronunciation…</div>}

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
          {result.tips.length > 0 && (
            <ul className="tips">
              {result.tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          )}
          {result.intonation && (
            <div className="intonation-wrap">
              <IntonationChart {...result.intonation} />
            </div>
          )}
        </div>
      )}

      <ActionBar
        level={rec.level}
        left={
          (onPrev || onNext) && (
            <button onClick={onPrev} disabled={!onPrev} title="Previous (←)">
              ← Back
            </button>
          )
        }
        center={
          <>
            <button onClick={() => listen("normal")} title="Listen (L)">
              🔊 Listen
            </button>
            <button onClick={() => listen("slow")} title="Listen slowly (S)">
              🐢 Slow
            </button>
            <button
              className={`record ${rec.recording ? "on" : ""}`}
              onClick={toggleRecord}
              disabled={busy}
              title="Record (Space)"
            >
              {rec.recording ? "■ Stop" : busy ? "Checking…" : result ? "🎙 Again" : "🎙 Say it"}
            </button>
            <button onClick={() => myAudioUrl && audio.play(myAudioUrl)} disabled={!myAudioUrl} title="Play your recording (P)">
              ▶ You
            </button>
          </>
        }
        right={
          onNext && (
            <button className={result ? "primary" : ""} onClick={onNext} title="Next (Enter)">
              {nextLabel}
            </button>
          )
        }
        hint={
          rec.recording ? (
            "Listening… stops automatically when you pause, or press Space."
          ) : busy ? (
            "Checking your pronunciation…"
          ) : (
            <>
              <kbd>Space</kbd> record · <kbd>L</kbd> listen · <kbd>S</kbd> slow · <kbd>P</kbd> your recording
              {onNext && (
                <>
                  {" "}
                  · <kbd>Enter</kbd> next
                </>
              )}
              {" · "}
              <AutoPlayToggle />
            </>
          )
        }
      />
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
