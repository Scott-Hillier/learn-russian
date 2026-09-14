import { useEffect, useMemo, useState } from "react";
import { api, type Health, type Phrase } from "./api";
import PracticeCard from "./PracticeCard";
import Stressed from "./Stressed";

export default function App() {
  const [phrases, setPhrases] = useState<Phrase[]>([]);
  const [current, setCurrent] = useState<Phrase | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [custom, setCustom] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .phrases()
      .then((p) => {
        setPhrases(p);
        setCurrent(p[0] ?? null);
      })
      .catch(() => setLoadError("Can't reach the backend. Is ./start.sh running?"));
  }, []);

  // Poll until the speech models have finished loading.
  useEffect(() => {
    let timer: number;
    const poll = () =>
      api
        .health()
        .then((h) => {
          setHealth(h);
          if (!h.asr_loaded) timer = window.setTimeout(poll, 2000);
        })
        .catch(() => (timer = window.setTimeout(poll, 3000)));
    poll();
    return () => clearTimeout(timer);
  }, []);

  const grouped = useMemo(() => {
    const map = new Map<string, Phrase[]>();
    for (const p of phrases) map.set(p.category, [...(map.get(p.category) ?? []), p]);
    return [...map.entries()];
  }, [phrases]);

  const index = current ? phrases.findIndex((p) => p.id === current.id) : -1;
  const go = (delta: number) => {
    if (index < 0) return;
    const next = phrases[(index + delta + phrases.length) % phrases.length];
    setCurrent(next);
  };

  const practiceCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = custom.trim();
    if (!text) return;
    const d = await api.describe(text);
    setCurrent({ ...d, id: -1, category: "Custom", english: "" });
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>
          <Stressed text="Говори́!" /> <small>Speak Russian</small>
        </h1>
        <form className="custom" onSubmit={practiceCustom}>
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Practise your own text…"
            lang="ru"
          />
          <small>Tip: mark stress with + before the vowel, e.g. прив+ет</small>
        </form>
        {grouped.map(([category, items]) => (
          <section key={category}>
            <h2>{category}</h2>
            <ul>
              {items.map((p) => (
                <li key={p.id}>
                  <button
                    className={current?.id === p.id ? "active" : ""}
                    onClick={() => setCurrent(p)}
                  >
                    <Stressed text={p.display} />
                    <small>{p.english}</small>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </aside>

      <main>
        {loadError && <div className="banner error">{loadError}</div>}
        {health && !health.asr_loaded && (
          <div className="banner">Loading speech models… (first start can take a minute)</div>
        )}
        {current && (
          <PracticeCard
            key={`${current.id}-${current.text}`}
            phrase={current}
            onPrev={() => go(-1)}
            onNext={() => go(1)}
            showNav={current.id >= 0}
          />
        )}
        <footer>
          {health ? `Voice: ${health.tts} · Recognition: ${health.asr_model.split("/").pop()}` : "Connecting…"}
          {" · "}Shortcuts: <kbd>L</kbd> listen <kbd>S</kbd> slow <kbd>Space</kbd> record <kbd>←</kbd>
          <kbd>→</kbd> phrases
        </footer>
      </main>
    </div>
  );
}
