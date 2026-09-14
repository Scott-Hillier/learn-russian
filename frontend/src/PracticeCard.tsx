import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AttemptResult, type Phrase } from "./api";
import Stressed from "./Stressed";
import { useRecorder } from "./useRecorder";

interface Props {
  phrase: Phrase;
  onPrev: () => void;
  onNext: () => void;
  showNav: boolean;
}

export default function PracticeCard({ phrase, onPrev, onNext, showNav }: Props) {
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [myAudioUrl, setMyAudioUrl] = useState<string | null>(null);
  const [best, setBest] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement>(new Audio());

  const play = useCallback((src: string) => {
    const a = audioRef.current;
    a.pause();
    a.src = src;
    a.play().catch(() => setError("Couldn't play audio."));
  }, []);

  const listen = useCallback(
    (speed: "normal" | "slow") => play(api.ttsUrl(phrase.text, speed)),
    [phrase.text, play],
  );

  const onRecorded = useCallback(
    async (blob: Blob) => {
      setMyAudioUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
      setChecking(true);
      setError(null);
      try {
        const r = await api.attempt(phrase.text, blob);
        setResult(r);
        setBest((b) => Math.max(b ?? 0, r.score));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setChecking(false);
      }
    },
    [phrase.text],
  );

  const rec = useRecorder(onRecorded);

  const toggleRecord = useCallback(() => {
    if (rec.recording) rec.stop();
    else if (!checking) {
      audioRef.current.pause();
      setResult(null);
      rec.start();
    }
  }, [rec, checking]);

  // Keyboard shortcuts (ignored while typing in an input).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.code === "Space") {
        e.preventDefault();
        toggleRecord();
      } else if (e.key === "l") listen("normal");
      else if (e.key === "s") listen("slow");
      else if (e.key === "ArrowRight" && showNav) onNext();
      else if (e.key === "ArrowLeft" && showNav) onPrev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleRecord, listen, onNext, onPrev, showNav]);

  useEffect(() => () => audioRef.current.pause(), []);

  const statusWord = (score: number) =>
    score >= 90 ? "Excellent!" : score >= 70 ? "Good. Almost there" : score >= 40 ? "Keep going" : "Let's try again";

  return (
    <div className="card">
      <div className="card-top">
        <span className="category">{phrase.category}</span>
        {best !== null && <span className="best">Best: {best}%</span>}
      </div>

      <div className="target" lang="ru">
        {result
          ? result.words.map((w, i) => (
              <span key={i} className={`word ${w.status}`} title={w.heard ? `heard: ${w.heard}` : "not heard"}>
                <Stressed text={w.target} />
              </span>
            ))
          : <Stressed text={phrase.display} />}
      </div>
      <div className="translit">{phrase.translit}</div>
      {phrase.sounds_like && (
        <div className="sounds-like">
          sounds like <strong>{phrase.sounds_like}</strong>
        </div>
      )}
      {phrase.english && <div className="english">“{phrase.english}”</div>}
      {phrase.note && <div className="note">💡 {phrase.note}</div>}

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
            <div className={`score s${Math.floor(result.score / 34)}`}>{result.score}%</div>
            <div>
              <strong>{statusWord(result.score)}</strong>
              <div className="heard">
                I heard: <span lang="ru">{result.heard || "(nothing)"}</span>
              </div>
            </div>
          </div>
          <ul className="tips">
            {result.tips.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
          <div className="controls small">
            {myAudioUrl && <button onClick={() => play(myAudioUrl)}>▶ My recording</button>}
            <button onClick={() => listen("normal")}>▶ Native</button>
            {showNav && <button onClick={onNext}>Next phrase →</button>}
          </div>
        </div>
      )}

      {showNav && (
        <div className="nav">
          <button onClick={onPrev}>← Previous</button>
          <button onClick={onNext}>Next →</button>
        </div>
      )}
    </div>
  );
}
