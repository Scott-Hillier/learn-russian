import { useEffect, useMemo, useState } from "react";
import AddToDeck, { copyToDeck } from "./AddToDeck";
import { api, type Deck, type FlashCard } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";

type Sort = "recent" | "hardest";

interface Props {
  onReview: () => void;
  decks: Deck[];
  onDecksChanged: () => void;
}

/** The Learned words deck: every word you've started learning, most recent first. Words can be
 *  ticked here and added to any deck, e.g. one for the ones that keep slipping away. */
export default function LearnedPage({ onReview, decks, onDecksChanged }: Props) {
  const [cards, setCards] = useState<FlashCard[] | null>(null);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<Sort>("recent");
  const [selected, setSelected] = useState<number[]>([]);
  const [target, setTarget] = useState<Deck | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const audio = useAudio();

  useEffect(() => {
    api.learnedCards().then(setCards).catch((e) => setMessage({ kind: "error", text: e.message }));
  }, []);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const matching = !cards ? [] : !q ? cards : cards.filter((c) => [c.plain, c.english, c.tag].some((f) => f.toLowerCase().includes(q)));
    // The list arrives most-recently-learned first; "hardest" puts the words you keep forgetting on top.
    return sort === "hardest" ? [...matching].sort((a, b) => b.lapses - a.lapses) : matching;
  }, [cards, filter, sort]);

  const toggle = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const allVisibleSelected = visible.length > 0 && visible.every((c) => selected.includes(c.id));
  const toggleAllVisible = () =>
    setSelected((s) => {
      const ids = visible.map((c) => c.id);
      return allVisibleSelected ? s.filter((x) => !ids.includes(x)) : [...new Set([...s, ...ids])];
    });

  const quickAdd = async (card: FlashCard) => {
    if (!target) return;
    try {
      setMessage({ kind: "ok", text: await copyToDeck(target, [card.id]) });
      onDecksChanged();
    } catch (e) {
      setMessage({ kind: "error", text: (e as Error).message });
    }
  };

  return (
    <div className="deck-page">
      <header className="lesson-head">
        <h2>⭐ Learned words</h2>
        <p>
          Every word you've started learning, from all decks. Review them as often as you like: it doesn't change when
          the spaced-repetition reviews come round. Tick the ones you keep forgetting and add them to a deck of their
          own.
        </p>
        <div className="deck-actions">
          <button className="primary" onClick={onReview} disabled={!cards?.length}>
            {cards?.length ? `Review all ${cards.length} →` : "No learned words yet"}
          </button>
        </div>
      </header>

      {message && (
        <div className={`banner ${message.kind === "error" ? "error" : ""}`} onClick={() => setMessage(null)}>
          {message.text}
        </div>
      )}

      {cards === null ? (
        <div className="card">Loading…</div>
      ) : cards.length === 0 ? (
        <p className="muted">Learn your first group of words and they'll show up here.</p>
      ) : (
        <div className="card-table-wrap">
          <div className="table-tools">
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search learned words…" />
            <label className="sort">
              Sort
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                <option value="recent">Most recent</option>
                <option value="hardest">Forgotten most</option>
              </select>
            </label>
            <span className="muted">
              {visible.length} of {cards.length}
            </span>
          </div>

          <AddToDeck
            decks={decks}
            target={target}
            onTarget={setTarget}
            selected={selected}
            onCopied={(text) => setMessage({ kind: "ok", text })}
            onError={(text) => setMessage({ kind: "error", text })}
            onDecksChanged={onDecksChanged}
            onClearSelection={() => setSelected([])}
          />

          <table className="card-table">
            <thead>
              <tr>
                <th className="tick">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleAllVisible}
                    title="Select everything shown"
                  />
                </th>
                <th>Russian</th>
                <th>English</th>
                <th>Forgotten</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((c) => (
                <tr key={c.id} className={selected.includes(c.id) ? "picked" : ""}>
                  <td className="tick">
                    <input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} />
                  </td>
                  <td>
                    <button className="icon" onClick={() => audio.play(api.ttsUrl(c.text, "normal"))} title="Listen">
                      🔊
                    </button>
                    <span className="table-ru">
                      <Stressed text={c.display} />
                    </span>
                  </td>
                  <td>
                    {c.english}
                    {c.tag && <div className="muted">{c.tag}</div>}
                  </td>
                  <td className="muted">{c.lapses > 0 ? `${c.lapses}×` : "—"}</td>
                  <td className="row-actions">
                    <button
                      onClick={() => quickAdd(c)}
                      disabled={!target}
                      title={target ? `Add to ${target.name}` : "Choose a deck above first"}
                    >
                      ＋ Add
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
