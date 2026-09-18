import { useCallback, useEffect, useState, type ComponentProps } from "react";
import { api, type Deck, type StudyStats } from "./api";
import DeckPage from "./DeckPage";
import Layout from "./Layout";
import LearnedPage from "./LearnedPage";
import StudySession from "./StudySession";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;
type View =
  | { kind: "home" }
  | { kind: "deck"; deckId: number }
  | { kind: "learned" }
  | { kind: "study"; deckId: number | null; learned?: boolean };

const MAX_GROUP_SIZE = 100;

export default function FlashcardsView({ layout }: { layout: LayoutProps }) {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [stats, setStats] = useState<StudyStats | null>(null);
  const [groupSize, setGroupSize] = useState<number | null>(null);
  const [view, setView] = useState<View>({ kind: "home" });
  const [newDeckName, setNewDeckName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.decks().then(setDecks).catch(() => setError("Can't reach the backend. Is ./start.sh running?"));
    api.studyStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    api.settings().then((s) => setGroupSize(s.group_size)).catch(() => {});
  }, [refresh]);

  const createDeck = async (name: string) => {
    if (!name.trim()) return;
    try {
      const deck = await api.createDeck(name);
      setNewDeckName("");
      refresh();
      setView({ kind: "deck", deckId: deck.id });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const saveGroupSize = async (value: number) => {
    setGroupSize(value);
    if (Number.isInteger(value) && value >= 1 && value <= MAX_GROUP_SIZE) {
      await api.updateSettings(value).catch((err) => setError(err.message));
      refresh();
    }
  };

  const learnedCount = stats?.learned_words ?? 0;
  const reviewLearned = () => setView({ kind: "study", deckId: null, learned: true });

  const sidebar = (
    <>
      <button
        className="study-all"
        onClick={() => setView({ kind: "study", deckId: null })}
        disabled={!stats || stats.due + stats.new === 0}
      >
        <strong>{stats ? `Learn group ${stats.group.number}` : "Study all decks"}</strong>
        <small>{stats ? `${stats.new} new · ${stats.due} due · all decks` : "…"}</small>
      </button>
      <h2>Decks</h2>
      <ul className="deck-list">
        <li>
          <button className={view.kind === "learned" ? "active" : ""} onClick={() => setView({ kind: "learned" })}>
            <span>⭐ Learned words</span>
            <small>
              {learnedCount} word{learnedCount === 1 ? "" : "s"} · review any time
            </small>
          </button>
        </li>
        {decks.map((d) => (
          <li key={d.id}>
            <button
              className={(view.kind === "deck" || view.kind === "study") && view.deckId === d.id ? "active" : ""}
              onClick={() => setView({ kind: "deck", deckId: d.id })}
            >
              <span>{d.name}</span>
              <small>
                Group {d.group.number} · <span className="count new">{Math.min(d.group.left, d.counts.new)} new</span>{" "}
                · <span className="count due">{d.counts.due} due</span>
              </small>
            </button>
          </li>
        ))}
      </ul>
      <form
        className="custom new-deck"
        onSubmit={(e) => {
          e.preventDefault();
          createDeck(newDeckName);
        }}
      >
        <input value={newDeckName} onChange={(e) => setNewDeckName(e.target.value)} placeholder="+ New deck name" />
      </form>
      <h2>Settings</h2>
      <label className="setting">
        Words per group
        <input
          type="number"
          min={1}
          max={MAX_GROUP_SIZE}
          value={groupSize ?? ""}
          onChange={(e) => saveGroupSize(Number(e.target.value))}
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
      {view.kind === "home" && (
        <Home
          stats={stats}
          decks={decks}
          onOpen={(id) => setView({ kind: "deck", deckId: id })}
          onOpenLearned={() => setView({ kind: "learned" })}
          onStudy={() => setView({ kind: "study", deckId: null })}
          onReviewLearned={reviewLearned}
          onCreateDeck={createDeck}
        />
      )}
      {view.kind === "learned" && <LearnedPage onReview={reviewLearned} decks={decks} onDecksChanged={refresh} />}
      {view.kind === "deck" && deckFor(view.deckId) && (
        <DeckPage
          key={view.deckId}
          deck={deckFor(view.deckId)!}
          decks={decks}
          onChanged={refresh}
          onStudy={() => setView({ kind: "study", deckId: view.deckId })}
          onReviewAll={() => setView({ kind: "study", deckId: view.deckId, learned: true })}
          onDeleted={() => {
            setView({ kind: "home" });
            refresh();
          }}
        />
      )}
      {view.kind === "study" && (
        <StudySession
          key={`study-${view.deckId}-${view.learned ? "learned" : "learn"}`}
          deckId={view.deckId}
          deckName={deckFor(view.deckId)?.name ?? (view.learned ? "Learned words" : "All decks")}
          learned={view.learned}
          onReviewed={refresh}
          onReviewLearned={reviewLearned}
          onExit={() => {
            refresh();
            setView(
              view.deckId
                ? { kind: "deck", deckId: view.deckId }
                : view.learned
                  ? { kind: "learned" }
                  : { kind: "home" },
            );
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
  onOpenLearned,
  onStudy,
  onReviewLearned,
  onCreateDeck,
}: {
  stats: StudyStats | null;
  decks: Deck[];
  onOpen: (id: number) => void;
  onOpenLearned: () => void;
  onStudy: () => void;
  onReviewLearned: () => void;
  onCreateDeck: (name: string) => void;
}) {
  const learnedCount = stats?.learned_words ?? 0;
  const [newName, setNewName] = useState<string | null>(null);
  return (
    <div className="overview">
      <h2>Flashcards</h2>
      <p>
        See the English, <strong>say the Russian out loud</strong>, then check yourself. New words come in{" "}
        <strong>groups</strong>: finish one and the next is ready straight away. Every word you learn goes into your{" "}
        <strong>Learned words</strong> deck, which you can review as often as you like.
      </p>
      {stats && (
        <div className="stat-row">
          <div className="stat">
            <strong>{stats.group.number}</strong>
            <span>
              current group · {stats.new} new left
            </span>
          </div>
          <div className="stat">
            <strong>{learnedCount}</strong>
            <span>learned words</span>
          </div>
          <div className="stat">
            <strong>{stats.due}</strong>
            <span>reviews due</span>
          </div>
          <div className="stat">
            <strong>{stats.streak_days}</strong>
            <span>day streak 🔥</span>
          </div>
        </div>
      )}
      <div className="controls">
        <button className="primary" onClick={onStudy} disabled={!stats || stats.due + stats.new === 0}>
          {!stats
            ? "Loading…"
            : stats.due + stats.new === 0
              ? "Every word learned 🎉"
              : stats.new > 0
                ? `Learn group ${stats.group.number} →`
                : "Do due reviews →"}
        </button>
        <button onClick={onReviewLearned} disabled={learnedCount === 0}>
          ⭐ Review learned words ({learnedCount})
        </button>
      </div>
      <div className="deck-grid">
        <button className="deck-tile" onClick={onOpenLearned}>
          <strong>⭐ Learned words</strong>
          <span className="muted">Every word you've learned so far. Review it any time.</span>
          <small>
            {learnedCount} word{learnedCount === 1 ? "" : "s"}
          </small>
        </button>
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
              Group {d.group.number} · {d.group.learned} learned · {d.counts.new} new
            </small>
          </button>
        ))}
        {newName === null ? (
          <button className="deck-tile new-deck-tile" onClick={() => setNewName("")}>
            <strong>＋ New deck</strong>
            <span className="muted">Make your own deck, then fill it from any other deck or the Learned words.</span>
          </button>
        ) : (
          <form
            className="deck-tile new-deck-tile"
            onSubmit={(e) => {
              e.preventDefault();
              onCreateDeck(newName);
              setNewName(null);
            }}
          >
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Deck name"
              maxLength={80}
            />
            <div className="form-row">
              <button className="primary" disabled={!newName.trim()}>
                Create
              </button>
              <button type="button" onClick={() => setNewName(null)}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
