import { useCallback, useEffect, useState, type ComponentProps } from "react";
import { api, type Deck, type StudyStats } from "./api";
import DeckPage from "./DeckPage";
import Layout from "./Layout";
import StudySession from "./StudySession";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;
type View = { kind: "home" } | { kind: "deck"; deckId: number } | { kind: "study"; deckId: number | null };

export default function FlashcardsView({ layout }: { layout: LayoutProps }) {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [stats, setStats] = useState<StudyStats | null>(null);
  const [newPerDay, setNewPerDay] = useState<number | null>(null);
  const [view, setView] = useState<View>({ kind: "home" });
  const [newDeckName, setNewDeckName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.decks().then(setDecks).catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
    api.studyStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    api.settings().then((s) => setNewPerDay(s.new_per_day)).catch(() => {});
  }, [refresh]);

  const createDeck = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDeckName.trim()) return;
    try {
      const deck = await api.createDeck(newDeckName);
      setNewDeckName("");
      refresh();
      setView({ kind: "deck", deckId: deck.id });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const saveNewPerDay = async (value: number) => {
    setNewPerDay(value);
    if (Number.isInteger(value) && value >= 0 && value <= 100) {
      await api.updateSettings(value).catch((err) => setError(err.message));
      refresh();
    }
  };

  const sidebar = (
    <>
      <button
        className="study-all"
        onClick={() => setView({ kind: "study", deckId: null })}
        disabled={!stats || stats.due + stats.new === 0}
      >
        <strong>Study all decks</strong>
        <small>{stats ? `${stats.due} due · ${stats.new} new today` : "…"}</small>
      </button>
      <h2>Decks</h2>
      <ul className="deck-list">
        {decks.map((d) => (
          <li key={d.id}>
            <button
              className={view.kind !== "home" && view.deckId === d.id ? "active" : ""}
              onClick={() => setView({ kind: "deck", deckId: d.id })}
            >
              <span>{d.name}</span>
              <small>
                <span className="count due">{d.counts.due} due</span> ·{" "}
                <span className="count new">{d.counts.new} new</span> · {d.counts.total} cards
              </small>
            </button>
          </li>
        ))}
      </ul>
      <form className="custom new-deck" onSubmit={createDeck}>
        <input value={newDeckName} onChange={(e) => setNewDeckName(e.target.value)} placeholder="+ New deck name" />
      </form>
      <h2>Settings</h2>
      <label className="setting">
        New cards per day
        <input
          type="number"
          min={0}
          max={100}
          value={newPerDay ?? ""}
          onChange={(e) => saveNewPerDay(Number(e.target.value))}
        />
      </label>
    </>
  );

  const deckFor = (id: number | null) => decks.find((d) => d.id === id) ?? null;

  return (
    <Layout {...layout} sidebar={sidebar}>
      {error && (
        <div className="banner error" onClick={() => setError(null)}>
          {error}
        </div>
      )}
      {view.kind === "home" && <Home stats={stats} decks={decks} onOpen={(id) => setView({ kind: "deck", deckId: id })} onStudy={() => setView({ kind: "study", deckId: null })} />}
      {view.kind === "deck" && deckFor(view.deckId) && (
        <DeckPage
          key={view.deckId}
          deck={deckFor(view.deckId)!}
          onChanged={refresh}
          onStudy={() => setView({ kind: "study", deckId: view.deckId })}
          onDeleted={() => {
            setView({ kind: "home" });
            refresh();
          }}
        />
      )}
      {view.kind === "study" && (
        <StudySession
          key={`study-${view.deckId}`}
          deckId={view.deckId}
          deckName={deckFor(view.deckId)?.name ?? "All decks"}
          onReviewed={refresh}
          onExit={() => {
            refresh();
            setView(view.deckId ? { kind: "deck", deckId: view.deckId } : { kind: "home" });
          }}
        />
      )}
    </Layout>
  );
}

function Home({
  stats,
  decks,
  onOpen,
  onStudy,
}: {
  stats: StudyStats | null;
  decks: Deck[];
  onOpen: (id: number) => void;
  onStudy: () => void;
}) {
  return (
    <div className="overview">
      <h2>Flashcards</h2>
      <p>
        See the English, <strong>say the Russian out loud</strong>, then check yourself. Your pronunciation score
        suggests how well you knew it, and spaced repetition (FSRS) brings each card back just before you'd forget it.
      </p>
      {stats && (
        <div className="stat-row">
          <div className="stat">
            <strong>{stats.due}</strong>
            <span>due now</span>
          </div>
          <div className="stat">
            <strong>{stats.new}</strong>
            <span>new today</span>
          </div>
          <div className="stat">
            <strong>{stats.reviewed_today}</strong>
            <span>reviewed today</span>
          </div>
          <div className="stat">
            <strong>{stats.streak_days}</strong>
            <span>day streak 🔥</span>
          </div>
        </div>
      )}
      <div>
        <button className="primary" onClick={onStudy} disabled={!stats || stats.due + stats.new === 0}>
          {stats && stats.due + stats.new === 0 ? "All done for today 🎉" : "Start studying →"}
        </button>
      </div>
      <div className="deck-grid">
        {decks.map((d) => (
          <button key={d.id} className="deck-tile" onClick={() => onOpen(d.id)}>
            <strong>{d.name}</strong>
            <span className="muted">{d.description || `${d.counts.total} cards`}</span>
            <span className="deck-bar" aria-hidden>
              <span className="review" style={{ flex: d.counts.review }} />
              <span className="learning" style={{ flex: d.counts.learning }} />
              <span className="new" style={{ flex: d.counts.new }} />
            </span>
            <small>
              {d.counts.review} learned · {d.counts.learning} learning · {d.counts.new} new
            </small>
          </button>
        ))}
      </div>
    </div>
  );
}
