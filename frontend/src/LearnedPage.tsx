import { useEffect, useMemo, useState } from "react";
import { api, type FlashCard } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";

/** The Learned words deck: every word you've learned from any deck, most recent first. */
export default function LearnedPage({ onReview }: { onReview: () => void }) {
  const [cards, setCards] = useState<FlashCard[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const audio = useAudio();

  useEffect(() => {
    api.learnedCards().then(setCards).catch((e) => setError(e.message));
  }, []);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!cards || !q) return cards ?? [];
    return cards.filter((c) => [c.plain, c.english, c.tag].some((f) => f.toLowerCase().includes(q)));
  }, [cards, filter]);

  return (
    <div className="deck-page">
      <header className="lesson-head">
        <h2>⭐ Learned words</h2>
        <p>
          Every word you've learned, from all decks. Finishing a group adds its words here. Review them as often as
          you like: it doesn't change when the spaced-repetition reviews come round.
        </p>
        <div className="deck-actions">
          <button className="primary" onClick={onReview} disabled={!cards?.length}>
            {cards?.length ? `Review all ${cards.length} →` : "No learned words yet"}
          </button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      {cards === null ? (
        <div className="card">Loading…</div>
      ) : cards.length === 0 ? (
        <p className="muted">Learn your first group of words and they'll show up here.</p>
      ) : (
        <div className="card-table-wrap">
          <div className="table-tools">
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search learned words…" />
            <span className="muted">
              {visible.length} of {cards.length}
            </span>
          </div>
          <table className="card-table">
            <thead>
              <tr>
                <th>Russian</th>
                <th>English</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((c) => (
                <tr key={c.id}>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
