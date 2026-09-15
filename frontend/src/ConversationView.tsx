import { useCallback, useEffect, useRef, useState, type ComponentProps } from "react";
import { api, type AttemptResult, type ChatCheck, type ChatStatus, type Scenario } from "./api";
import Layout from "./Layout";
import Stressed, { stressToDisplay } from "./Stressed";
import { useAudio } from "./useAudio";
import { useHotkeys } from "./useHotkeys";
import { useRecorder } from "./useRecorder";
import { Letters } from "./WordFeedback";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;

interface Message {
  id: number;
  role: "partner" | "learner";
  text: string;
  english?: string;
  suggestions?: { russian: string; english: string }[];
  clarity?: AttemptResult | null; // spoken learner messages
  check?: ChatCheck | "pending" | "failed";
}

const SAVE_DECK = "Conversation phrases";
const CYRILLIC = /[а-яё]/i;
let nextId = 1;

function opening(s: Scenario): Message[] {
  return [{ id: nextId++, role: "partner", text: s.opening.plain, english: s.opening.english }];
}

export default function ConversationView({ layout }: { layout: LayoutProps }) {
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [chats, setChats] = useState<Record<string, Message[]>>({});
  const [level, setLevel] = useState("beginner");
  const [showEnglish, setShowEnglish] = useState(true);
  const [autoPlay, setAutoPlay] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(() => {
    api.chatStatus().then(setStatus).catch(() => setStatus({ running: false, installed: false, model: "" }));
  }, []);

  useEffect(() => {
    refreshStatus();
    api
      .scenarios()
      .then((s) => {
        setScenarios(s);
        setScenarioId((id) => id ?? s[0]?.id ?? null);
        setChats((c) => Object.fromEntries(s.map((sc) => [sc.id, c[sc.id] ?? opening(sc)])));
      })
      .catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
  }, [refreshStatus]);

  const scenario = scenarios.find((s) => s.id === scenarioId) ?? null;
  const ready = status?.running && status.installed;

  const sidebar = (
    <>
      <h2>Scenarios</h2>
      <ul className="lesson-list">
        {scenarios.map((s) => (
          <li key={s.id}>
            <button className={s.id === scenarioId ? "active" : ""} onClick={() => setScenarioId(s.id)}>
              <span>
                {s.emoji} {s.title}
              </span>
              <small>{(chats[s.id]?.length ?? 1) > 1 ? `${chats[s.id].length} messages` : "not started"}</small>
            </button>
          </li>
        ))}
      </ul>
      <h2>Options</h2>
      <label className="setting">
        Level
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="beginner">Beginner</option>
          <option value="elementary">Elementary</option>
        </select>
      </label>
      <label className="setting">
        Show English
        <input type="checkbox" checked={showEnglish} onChange={(e) => setShowEnglish(e.target.checked)} />
      </label>
      <label className="setting">
        Auto-play replies
        <input type="checkbox" checked={autoPlay} onChange={(e) => setAutoPlay(e.target.checked)} />
      </label>
      <p className="sidebar-note">
        {status ? (ready ? `Local AI: ${status.model} ✓` : "Local AI not available") : "Checking local AI…"}
      </p>
    </>
  );

  return (
    <Layout {...layout} sidebar={sidebar}>
      {error && <div className="banner error">{error}</div>}
      {status && !ready && <SetupCard status={status} onRetry={refreshStatus} />}
      {scenario && ready && (
        <Chat
          key={scenario.id}
          scenario={scenario}
          messages={chats[scenario.id] ?? []}
          setMessages={(update) => setChats((c) => ({ ...c, [scenario.id]: update(c[scenario.id] ?? []) }))}
          level={level}
          showEnglish={showEnglish}
          autoPlay={autoPlay}
          onRestart={() => setChats((c) => ({ ...c, [scenario.id]: opening(scenario) }))}
        />
      )}
    </Layout>
  );
}

function SetupCard({ status, onRetry }: { status: ChatStatus; onRetry: () => void }) {
  return (
    <div className="card setup-card">
      <h2>Set up the local AI partner</h2>
      <p>The conversation partner runs entirely on your Mac using Ollama. It needs a one-time setup:</p>
      <ol>
        <li className={status.running ? "done" : ""}>
          Install and start Ollama: <code>brew install ollama</code> then <code>ollama serve</code>{" "}
          {status.running && "✓"}
        </li>
        <li className={status.installed ? "done" : ""}>
          Download the model (about 3 GB): <code>ollama pull {status.model || "gemma3:4b"}</code>
        </li>
      </ol>
      <p className="muted">Running ./start.sh does both automatically if Ollama is installed.</p>
      <div className="controls">
        <button className="record" onClick={onRetry}>
          Check again
        </button>
      </div>
    </div>
  );
}

interface ChatProps {
  scenario: Scenario;
  messages: Message[];
  setMessages: (update: (m: Message[]) => Message[]) => void;
  level: string;
  showEnglish: boolean;
  autoPlay: boolean;
  onRestart: () => void;
}

function Chat({ scenario, messages, setMessages, level, showEnglish, autoPlay, onRestart }: ChatProps) {
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [practice, setPractice] = useState<{ text: string; result?: AttemptResult; checking?: boolean } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const audio = useAudio(setNotice);
  const endRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, thinking]);

  const update = (id: number, patch: Partial<Message>) =>
    setMessages((ms) => ms.map((m) => (m.id === id ? { ...m, ...patch } : m)));

  const send = async (text: string, clarity?: AttemptResult | null) => {
    text = text.trim();
    if (!text || thinking) return;
    const learner: Message = { id: nextId++, role: "learner", text, clarity, check: CYRILLIC.test(text) ? "pending" : undefined };
    const history = [...messagesRef.current, learner].map((m) => ({ role: m.role, text: m.text }));
    setMessages((ms) => [...ms, learner]);
    setDraft("");
    setPractice(null);
    setThinking(true);
    setNotice(null);

    // Ollama handles one request at a time on this Mac, so ask for the reply first and the grammar
    // check second: the conversation keeps moving and the correction appears a few seconds later.
    const replyRequest = api.chatReply(scenario.id, history, level);
    if (learner.check) {
      api
        .chatCheck(text)
        .then((check) => update(learner.id, { check }))
        .catch(() => update(learner.id, { check: "failed" }));
    }
    try {
      const r = await replyRequest;
      setMessages((ms) => [
        ...ms,
        { id: nextId++, role: "partner", text: r.reply, english: r.translation, suggestions: r.suggestions },
      ]);
      if (autoPlay) audio.play(api.ttsUrl(r.reply, "normal"));
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setThinking(false);
    }
  };

  // Free speech → transcript → send. Practising a suggestion → pronunciation score first.
  // useRecorder always calls the latest version of this handler, so it needn't be memoised.
  const onRecorded = async (blob: Blob) => {
      if (practice) {
        setPractice({ ...practice, checking: true });
        try {
          const result = await api.attempt(practice.text, blob, "custom");
          setPractice({ text: practice.text, result });
        } catch (e) {
          setNotice((e as Error).message);
          setPractice({ text: practice.text });
        }
        return;
      }
      setTranscribing(true);
      try {
        const t = await api.chatTranscribe(blob);
        if (!t.text.trim()) setNotice("I didn't catch that. Try again, a little louder.");
        else await send(t.text, t.clarity);
      } catch (e) {
        setNotice((e as Error).message);
      } finally {
        setTranscribing(false);
      }
  };
  const rec = useRecorder(onRecorded);

  const toggleRecord = () => {
    if (rec.recording) rec.stop();
    else if (!thinking && !transcribing) {
      audio.stop();
      rec.start();
    }
  };

  useHotkeys((key) => {
    if (key !== "space") return false;
    toggleRecord();
    return true;
  });

  const save = async (m: Message) => {
    try {
      const decks = await api.decks();
      const deck = decks.find((d) => d.name === SAVE_DECK) ?? (await api.createDeck(SAVE_DECK, "Phrases saved from conversations."));
      await api.addCard(deck.id, { russian: m.text, english: m.english ?? "", notes: scenario.title });
      setNotice(`Saved to the “${SAVE_DECK}” flashcard deck.`);
    } catch (e) {
      setNotice((e as Error).message.includes("already") ? "Already in your deck." : (e as Error).message);
    }
  };

  const lastPartner = [...messages].reverse().find((m) => m.role === "partner");

  return (
    <div className="chat-page">
      <header className="lesson-head chat-head">
        <div>
          <h2>
            {scenario.emoji} {scenario.title}
          </h2>
          <p>
            You're talking to {scenario.role}. <strong>Try to:</strong> {scenario.goals.join(" · ")}
          </p>
        </div>
        <button className="link" onClick={onRestart}>
          ↻ Start over
        </button>
      </header>

      <details className="phrasebook">
        <summary>Useful phrases</summary>
        <div className="chips">
          {scenario.phrases.map((p) => (
            <button key={p.text} className="chip" onClick={() => setPractice({ text: p.text })} title={p.english}>
              <Stressed text={p.display} /> <small className="muted">{p.english}</small>
            </button>
          ))}
        </div>
      </details>

      <div className="chat-log">
        {messages.map((m) => (
          <div key={m.id} className={`bubble-row ${m.role}`}>
            <div className={`bubble ${m.role}`}>
              <div className="bubble-text" lang="ru">
                {m.text}
              </div>
              {m.role === "partner" && showEnglish && m.english && <div className="bubble-english">{m.english}</div>}
              {m.role === "partner" && (
                <div className="bubble-actions">
                  <button onClick={() => audio.play(api.ttsUrl(m.text, "normal"))} title="Listen">
                    🔊
                  </button>
                  <button onClick={() => audio.play(api.ttsUrl(m.text, "slow"))} title="Listen slowly">
                    🐢
                  </button>
                  <button onClick={() => setPractice({ text: m.text })} title="Practise saying this">
                    🎙
                  </button>
                  <button onClick={() => save(m)} title="Save to flashcards">
                    ⭐
                  </button>
                </div>
              )}
              {m.role === "learner" && <LearnerNotes message={m} />}
            </div>
          </div>
        ))}
        {thinking && (
          <div className="bubble-row partner">
            <div className="bubble partner typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {lastPartner?.suggestions && lastPartner.suggestions.length > 0 && !thinking && (
        <div className="suggestions">
          <span className="muted">You could say:</span>
          {lastPartner.suggestions.map((s) => (
            <button key={s.russian} className="chip" onClick={() => setPractice({ text: s.russian })} title={s.english}>
              <span lang="ru">{s.russian}</span> <small className="muted">{s.english}</small>
            </button>
          ))}
        </div>
      )}

      {practice && (
        <div className="practice-panel">
          <div className="practice-text" lang="ru">
            {practice.result ? (
              practice.result.words.map((w, i) => (
                <span key={i} className={`word ${w.status}`}>
                  <Letters letters={w.letters} />
                </span>
              ))
            ) : (
              <Stressed text={stressToDisplay(practice.text)} />
            )}
          </div>
          <div className="controls small">
            <button onClick={() => audio.play(api.ttsUrl(practice.text, "slow"))}>🐢 Hear it</button>
            <button className={`record ${rec.recording ? "on" : ""}`} onClick={toggleRecord} disabled={practice.checking}>
              {rec.recording ? "■ Stop" : practice.checking ? "Checking…" : "🎙 Practise"}
            </button>
            {practice.result && (
              <span className={`pill ${practice.result.score >= 85 ? "good" : practice.result.score >= 55 ? "close" : "wrong"}`}>
                {practice.result.score}%
              </span>
            )}
            <button className="record" onClick={() => send(practice.text.replace(/\+/g, ""), practice.result)} disabled={thinking}>
              Send ➤
            </button>
            <button onClick={() => setPractice(null)}>✕</button>
          </div>
        </div>
      )}

      {notice && (
        <div className="banner" onClick={() => setNotice(null)}>
          {notice}
        </div>
      )}

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <button
          type="button"
          className={`mic ${rec.recording && !practice ? "on" : ""}`}
          onClick={() => {
            setPractice(null);
            toggleRecord();
          }}
          disabled={thinking || transcribing || (rec.recording && !!practice)}
          title="Speak (Space)"
        >
          {rec.recording && !practice ? "■" : transcribing ? "…" : "🎙"}
        </button>
        <input
          lang="ru"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={transcribing ? "Listening to what you said…" : "Speak (Space) or type in Russian…"}
        />
        <button className="primary" disabled={!draft.trim() || thinking}>
          Send
        </button>
      </form>
      <div className="meter" aria-hidden>
        <div style={{ width: `${rec.level * 100}%` }} />
      </div>
    </div>
  );
}

function LearnerNotes({ message }: { message: Message }) {
  const { clarity, check } = message;
  return (
    <>
      {clarity && (
        <div className="bubble-note">
          Clarity{" "}
          <span className={`pill ${clarity.score >= 85 ? "good" : clarity.score >= 55 ? "close" : "wrong"}`}>
            {clarity.score}%
          </span>
        </div>
      )}
      {check === "pending" && <div className="bubble-note muted">Checking grammar…</div>}
      {check && check !== "pending" && check !== "failed" && check.status === "correct" && (
        <div className="bubble-note">✓ Looks correct</div>
      )}
      {check && check !== "pending" && check !== "failed" && check.status === "corrected" && (
        <div className="bubble-note correction" title="Suggested by the local AI. It can occasionally be wrong.">
          ✎ Better:{" "}
          <span lang="ru">
            {check.diff
              .filter((d) => d.kind !== "removed")
              .map((d, i) => (
                <span key={i} className={d.kind === "changed" ? "changed" : ""}>
                  {d.text}{" "}
                </span>
              ))}
          </span>
        </div>
      )}
    </>
  );
}
