import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import { api, type AttemptResult, type Phrase, type Sentence } from "./api";
import Drill from "./Drill";
import Layout from "./Layout";
import PracticeCard, { TimingNote } from "./PracticeCard";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";
import { useRecorder } from "./useRecorder";
import { Letters } from "./WordFeedback";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;
type Step = "listen" | "words" | "chunks" | "full" | "shadow";

const STEPS: { id: Step; label: string }[] = [
  { id: "listen", label: "1 · Listen" },
  { id: "words", label: "2 · Words" },
  { id: "chunks", label: "3 · Chunks" },
  { id: "full", label: "4 · Full sentence" },
  { id: "shadow", label: "5 · Shadow" },
];

export default function SentencesView({ layout }: { layout: LayoutProps }) {
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [best, setBest] = useState<Record<string, number>>({});
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshBest = useCallback(() => {
    api.bestScores("sentence").then(setBest).catch(() => {});
  }, []);

  useEffect(() => {
    api
      .sentences()
      .then((s) => {
        setSentences(s);
        setCurrentId((id) => id ?? s[0]?.id ?? null);
      })
      .catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
    refreshBest();
  }, [refreshBest]);

  const themes = useMemo(() => {
    const map = new Map<string, Sentence[]>();
    for (const s of sentences) map.set(s.theme, [...(map.get(s.theme) ?? []), s]);
    return [...map.entries()];
  }, [sentences]);

  const current = sentences.find((s) => s.id === currentId) ?? null;
  const nextSentence = current ? sentences[(sentences.indexOf(current) + 1) % sentences.length] : null;

  const sidebar = (
    <>
      {themes.map(([theme, items]) => (
        <section key={theme}>
          <h2>{theme}</h2>
          <ul>
            {items.map((s) => (
              <li key={s.id}>
                <button className={s.id === currentId ? "active" : ""} onClick={() => setCurrentId(s.id)}>
                  <span className="sentence-row">
                    <Stressed text={s.display} />
                    {best[s.text] !== undefined && (
                      <span className={`pill ${best[s.text] >= 85 ? "good" : best[s.text] >= 55 ? "close" : "wrong"}`}>
                        {best[s.text]}%
                      </span>
                    )}
                  </span>
                  <small>{s.english}</small>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );

  return (
    <Layout {...layout} sidebar={sidebar}>
      {error && <div className="banner error">{error}</div>}
      {current && (
        <SentenceTrainer
          key={current.id}
          sentence={current}
          onResult={refreshBest}
          onNextSentence={nextSentence ? () => setCurrentId(nextSentence.id) : undefined}
        />
      )}
    </Layout>
  );
}

function asPhrase(item: { text: string; display: string; plain: string; translit: string }, category: string, english = ""): Phrase {
  return { ...item, id: 0, category, english };
}

interface TrainerProps {
  sentence: Sentence;
  onResult: () => void;
  onNextSentence?: () => void;
}

function SentenceTrainer({ sentence, onResult, onNextSentence }: TrainerProps) {
  const [step, setStep] = useState<Step>("listen");
  const audio = useAudio();
  const play = (text: string, speed: "normal" | "slow" = "normal") => audio.play(api.ttsUrl(text, speed));

  // Very short words (я, в, у…) are unreliable to score on their own; they're practised inside chunks.
  const practiceWords = sentence.words.filter((w) => w.plain.length >= 3);
  const hasChunks = sentence.chunks.length > 1;
  const stepAfter: Record<Step, Step | null> = {
    listen: practiceWords.length ? "words" : hasChunks ? "chunks" : "full",
    words: hasChunks ? "chunks" : "full",
    chunks: "full",
    full: "shadow",
    shadow: null,
  };
  const nextLabel = (s: Step) => {
    const n = stepAfter[s];
    return n ? `Next: ${STEPS.find((x) => x.id === n)!.label.split("· ")[1].toLowerCase()} →` : "";
  };

  return (
    <div className="lesson">
      <header className="lesson-head">
        <h2>
          <Stressed text={sentence.display} />
        </h2>
        <p>“{sentence.english}”</p>
        <div className="tabs">
          {STEPS.map((s) => (
            <button
              key={s.id}
              className={step === s.id ? "active" : ""}
              onClick={() => setStep(s.id)}
              disabled={(s.id === "words" && !practiceWords.length) || (s.id === "chunks" && !hasChunks)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </header>

      {step === "listen" && (
        <div className="card">
          <div className="target" lang="ru">
            <Stressed text={sentence.display} />
          </div>
          <div className="translit">{sentence.translit}</div>
          <div className="english">“{sentence.english}”</div>
          <div className="controls">
            <button onClick={() => play(sentence.text)}>🔊 Listen</button>
            <button onClick={() => play(sentence.text, "slow")}>🐢 Slow</button>
          </div>
          <h3 className="section-label">Word by word (click to hear)</h3>
          <div className="gloss-grid">
            {sentence.words.map((w, i) => (
              <button key={i} className="gloss" onClick={() => play(w.text, "slow")}>
                <span className="gloss-ru">
                  <Stressed text={w.display} />
                </span>
                <span className="muted">{w.translit}</span>
                <span className="gloss-en">{w.gloss}</span>
              </button>
            ))}
          </div>
          <div className="controls">
            <button className="record" onClick={() => setStep(stepAfter.listen!)}>
              {nextLabel("listen")}
            </button>
          </div>
        </div>
      )}

      {step === "words" && (
        <Drill
          key="words"
          items={practiceWords.map((w) => ({ phrase: asPhrase(w, "Word", w.gloss) }))}
          source="custom"
          onFinish={() => setStep(stepAfter.words!)}
          finishLabel={nextLabel("words")}
        />
      )}

      {step === "chunks" && (
        <Drill
          key="chunks"
          items={sentence.chunks.map((c) => ({ phrase: asPhrase(c, "Chunk") }))}
          source="custom"
          onFinish={() => setStep("full")}
          finishLabel={nextLabel("chunks")}
        />
      )}

      {step === "full" && (
        <>
          <PracticeCard
            key="full"
            phrase={asPhrase(sentence, "Full sentence", sentence.english)}
            source="sentence"
            timing
            intonation
            onResult={onResult}
          />
          <div className="lesson-next">
            <button className="primary" onClick={() => setStep("shadow")}>
              {nextLabel("full")}
            </button>
          </div>
        </>
      )}

      {step === "shadow" && <ShadowCard sentence={sentence} onResult={onResult} onNextSentence={onNextSentence} />}
    </div>
  );
}

/** Shadowing: speak along with the native audio while it plays. */
function ShadowCard({ sentence, onResult, onNextSentence }: TrainerProps) {
  const [speed, setSpeed] = useState<"normal" | "slow">("normal");
  const [phase, setPhase] = useState<"idle" | "countdown" | "playing" | "checking">("idle");
  const [count, setCount] = useState(3);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mine, setMine] = useState<string | null>(null);
  const nativeRef = useRef<HTMLAudioElement | null>(null);
  const timers = useRef<number[]>([]);
  const replay = useAudio();

  const onRecorded = useCallback(
    async (blob: Blob) => {
      setMine((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
      setPhase("checking");
      try {
        // Timing only makes sense against normal-speed native audio.
        const r = await api.attempt(sentence.text, blob, "sentence", speed === "normal");
        setResult(r);
        onResult();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setPhase("idle");
      }
    },
    [sentence.text, speed, onResult],
  );
  const rec = useRecorder(onRecorded, { autoStop: false });

  useEffect(
    () => () => {
      timers.current.forEach(clearTimeout);
      nativeRef.current?.pause();
    },
    [],
  );

  const later = (fn: () => void, ms: number) => timers.current.push(window.setTimeout(fn, ms));

  const start = () => {
    setResult(null);
    setError(null);
    setPhase("countdown");
    setCount(3);
    later(() => setCount(2), 700);
    later(() => setCount(1), 1400);
    later(async () => {
      await rec.start();
      const native = new Audio(api.ttsUrl(sentence.text, speed));
      nativeRef.current = native;
      native.onended = () => later(() => rec.stop(), 900);
      native.onerror = () => {
        setError("Couldn't play the native audio.");
        rec.stop();
      };
      later(() => {
        setPhase("playing");
        native.play().catch(() => {
          setError("Couldn't play the native audio.");
          rec.stop();
        });
      }, 250);
    }, 2100);
  };

  return (
    <div className="card">
      <div className="card-top">
        <span className="category">Shadowing</span>
      </div>
      <p className="shadow-intro">
        🎧 <strong>Wear headphones</strong>, otherwise the microphone hears the native voice too. After the countdown,
        the sentence plays; <strong>speak along with it at the same time</strong>, matching its rhythm and melody.
      </p>
      <div className="target" lang="ru">
        {result ? (
          result.words.map((w, i) => (
            <span key={i} className={`word ${w.status}`}>
              <Letters letters={w.letters} />
            </span>
          ))
        ) : (
          <Stressed text={sentence.display} />
        )}
      </div>
      <div className="translit">{sentence.translit}</div>

      <div className="controls">
        <div className="segmented">
          <button className={speed === "slow" ? "active" : ""} onClick={() => setSpeed("slow")} disabled={phase !== "idle"}>
            🐢 Slow
          </button>
          <button className={speed === "normal" ? "active" : ""} onClick={() => setSpeed("normal")} disabled={phase !== "idle"}>
            Normal
          </button>
        </div>
        <button className={`record ${phase === "playing" ? "on" : ""}`} onClick={start} disabled={phase !== "idle"}>
          {phase === "countdown" ? `Get ready… ${count}` : phase === "playing" ? "Speak now!" : phase === "checking" ? "Checking…" : "▶ Start shadowing"}
        </button>
      </div>
      <div className="meter" aria-hidden>
        <div style={{ width: `${rec.level * 100}%` }} />
      </div>
      {(rec.error || error) && <div className="banner error">{rec.error || error}</div>}

      {result && (
        <div className="result">
          <div className="score-row">
            <div className={`score ${result.score >= 85 ? "good" : result.score >= 55 ? "close" : "wrong"}`}>
              {result.score}%
            </div>
            <div>
              <strong>{result.score >= 85 ? "Great shadowing!" : "Keep practising. Try the slow speed first."}</strong>
              <div className="heard">
                I heard: <span lang="ru">{result.heard || "(nothing)"}</span>
              </div>
              {result.timing && <TimingNote timing={result.timing} />}
            </div>
          </div>
          <ul className="tips">
            {result.tips.slice(0, 3).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
          <div className="controls small">
            {mine && <button onClick={() => replay.play(mine)}>▶ My recording</button>}
            <button onClick={() => replay.play(api.ttsUrl(sentence.text, speed))}>▶ Native</button>
            {onNextSentence && (
              <button className="record" onClick={onNextSentence}>
                Next sentence →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
