import { useEffect, useMemo, useState, type ComponentProps } from "react";
import { api, type Phrase } from "./api";
import Layout from "./Layout";
import PracticeCard from "./PracticeCard";
import Stressed from "./Stressed";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;

export default function PhrasesView({ layout }: { layout: LayoutProps }) {
  const [phrases, setPhrases] = useState<Phrase[]>([]);
  const [current, setCurrent] = useState<Phrase | null>(null);
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

  const grouped = useMemo(() => {
    const map = new Map<string, Phrase[]>();
    for (const p of phrases) map.set(p.category, [...(map.get(p.category) ?? []), p]);
    return [...map.entries()];
  }, [phrases]);

  const index = current ? phrases.findIndex((p) => p.id === current.id) : -1;
  const go = (delta: number) => {
    if (index < 0) return;
    setCurrent(phrases[(index + delta + phrases.length) % phrases.length]);
  };

  const practiceCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = custom.trim();
    if (!text) return;
    const d = await api.describe(text);
    setCurrent({ ...d, id: -1, category: "Custom", english: "" });
  };

  const sidebar = (
    <>
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
                <button className={current?.id === p.id ? "active" : ""} onClick={() => setCurrent(p)}>
                  <Stressed text={p.display} />
                  <small>{p.english}</small>
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
      {loadError && <div className="banner error">{loadError}</div>}
      {current && (
        <PracticeCard
          key={`${current.id}-${current.text}`}
          phrase={current}
          source={current.id >= 0 ? "phrase" : "custom"}
          onPrev={current.id >= 0 ? () => go(-1) : undefined}
          onNext={current.id >= 0 ? () => go(1) : undefined}
        />
      )}
    </Layout>
  );
}
