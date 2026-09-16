import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Deck, type FlashCard } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";

interface Props {
  deck: Deck;
  onChanged: () => void;
  onStudy: () => void;
  onDeleted: () => void;
}

const STATE_LABEL = { new: "New", learning: "Learning", review: "Learned" };

function dueLabel(card: FlashCard): string {
  if (card.suspended) return "suspended";
  if (card.state === "new" || card.due === null) return "—";
  const s = card.due - Date.now() / 1000;
  if (s <= 0) return "due now";
  if (s < 3600) return `in ${Math.round(s / 60)}m`;
  if (s < 86400) return `in ${Math.round(s / 3600)}h`;
  return `in ${Math.round(s / 86400)}d`;
}

export default function DeckPage({ deck, onChanged, onStudy, onDeleted }: Props) {
  const [cards, setCards] = useState<FlashCard[]>([]);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<FlashCard | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const audio = useAudio();

  const load = useCallback(() => {
    api.cards(deck.id).then(setCards).catch((e) => setMessage({ kind: "error", text: e.message }));
  }, [deck.id]);
  useEffect(load, [load]);

  const changed = () => {
    load();
    onChanged();
  };

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return cards;
    return cards.filter((c) =>
      [c.plain, c.english, c.tag].some((f) => f.toLowerCase().includes(q)),
    );
  }, [cards, filter]);

  const importFile = async (file: File) => {
    try {
      const r = await api.importCsv(deck.id, file);
      const parts = [`Imported ${r.added} card${r.added === 1 ? "" : "s"}`];
      if (r.skipped_duplicates) parts.push(`${r.skipped_duplicates} duplicates skipped`);
      if (r.errors.length) parts.push(`${r.errors.length} problems: ${r.errors.slice(0, 3).join(" ")}`);
      setMessage({ kind: r.errors.length ? "error" : "ok", text: parts.join(" · ") });
      changed();
    } catch (e) {
      setMessage({ kind: "error", text: (e as Error).message });
    }
  };

  const toggleSuspend = async (c: FlashCard) => {
    await api.updateCard(c.id, { russian: c.text, english: c.english, notes: c.notes, suspended: !c.suspended });
    changed();
  };

  const remove = async (c: FlashCard) => {
    if (!window.confirm(`Delete “${c.plain}”? Its review history is deleted too.`)) return;
    await api.deleteCard(c.id).catch((e) => setMessage({ kind: "error", text: e.message }));
    changed();
  };

  const deleteDeck = async () => {
    if (!window.confirm(`Delete the deck “${deck.name}” and all ${deck.counts.total} cards?`)) return;
    await api.deleteDeck(deck.id);
    onDeleted();
  };

  const newInGroup = Math.min(deck.group.left, deck.counts.new);
  const studyable = deck.counts.due + newInGroup > 0;

  return (
    <div className="deck-page">
      <header className="lesson-head">
        <h2>{deck.name}</h2>
        {deck.description && <p>{deck.description}</p>}
        <div className="deck-actions">
          <button className="primary" onClick={onStudy} disabled={!studyable}>
            {!studyable
              ? "Every word learned 🎉"
              : newInGroup > 0
                ? `Learn group ${deck.group.number} (${newInGroup} new · ${deck.counts.due} due)`
                : `Do due reviews (${deck.counts.due})`}
          </button>
          <button onClick={() => fileRef.current?.click()}>⬆ Import CSV</button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt,text/csv"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importFile(f);
              e.target.value = "";
            }}
          />
          {!deck.builtin && (
            <button className="danger" onClick={deleteDeck}>
              Delete deck
            </button>
          )}
        </div>
        <p className="muted small-print">
          CSV format: one card per line, <code>russian,english[,notes]</code>. Mark stress with + before the vowel
          (e.g. <code>молок+о,milk</code>).
        </p>
      </header>

      {message && (
        <div className={`banner ${message.kind === "error" ? "error" : ""}`} onClick={() => setMessage(null)}>
          {message.text}
        </div>
      )}

      <CardForm
        key={editing?.id ?? "new"}
        card={editing}
        onCancel={() => setEditing(null)}
        onSave={async (fields) => {
          try {
            if (editing) await api.updateCard(editing.id, { ...fields, suspended: editing.suspended });
            else await api.addCard(deck.id, fields);
            setEditing(null);
            setMessage({ kind: "ok", text: editing ? "Card updated." : `Added “${fields.russian.replace(/\+/g, "")}”.` });
            changed();
            return true;
          } catch (e) {
            setMessage({ kind: "error", text: (e as Error).message });
            return false;
          }
        }}
      />

      <div className="card-table-wrap">
        <div className="table-tools">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search cards…" />
          <span className="muted">
            {visible.length} of {cards.length}
          </span>
        </div>
        <table className="card-table">
          <thead>
            <tr>
              <th>Russian</th>
              <th>English</th>
              <th>Status</th>
              <th>Next review</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((c) => (
              <tr key={c.id} className={c.suspended ? "suspended" : ""}>
                <td>
                  <button className="icon" onClick={() => audio.play(api.ttsUrl(c.text, "normal"))} title="Listen">
                    🔊
                  </button>
                  <span className="table-ru">
                    <Stressed text={c.display} />
                  </span>
                  {c.needs_stress && (
                    <span className="stress-warn" title="No stress mark: add + before the stressed vowel">
                      ⚠
                    </span>
                  )}
                </td>
                <td>
                  {c.english}
                  {c.tag && <div className="muted">{c.tag}</div>}
                </td>
                <td>
                  <span className={`state-badge ${c.state}`}>{STATE_LABEL[c.state]}</span>
                </td>
                <td className="muted">{dueLabel(c)}</td>
                <td className="row-actions">
                  <button onClick={() => setEditing(c)}>Edit</button>
                  <button onClick={() => toggleSuspend(c)}>{c.suspended ? "Unsuspend" : "Suspend"}</button>
                  {!c.builtin && <button onClick={() => remove(c)}>Delete</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface FormProps {
  card: FlashCard | null;
  onSave: (fields: { russian: string; english: string; notes: string }) => Promise<boolean>;
  onCancel: () => void;
}

function CardForm({ card, onSave, onCancel }: FormProps) {
  const [russian, setRussian] = useState(card?.text ?? "");
  const [english, setEnglish] = useState(card?.english ?? "");
  const [notes, setNotes] = useState(card?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const audio = useAudio();

  const multiVowelWithoutStress = russian
    .split(/\s+/)
    .some((w) => [...w.toLowerCase()].filter((c) => "аеёиоуыэюя".includes(c)).length > 1 && !/[+ё]/i.test(w));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const ok = await onSave({ russian, english, notes });
    setSaving(false);
    if (ok && !card) {
      setRussian("");
      setEnglish("");
      setNotes("");
    }
  };

  return (
    <form className="card-form" onSubmit={submit}>
      <strong>{card ? "Edit card" : "Add a card"}</strong>
      <div className="form-row">
        <input lang="ru" value={russian} onChange={(e) => setRussian(e.target.value)} placeholder="Russian, e.g. кн+ига" required />
        <button
          type="button"
          className="icon"
          disabled={!russian.trim()}
          onClick={() => audio.play(api.ttsUrl(russian, "normal"))}
          title="Hear it (the voice guesses stress if unmarked)"
        >
          🔊
        </button>
        <input value={english} onChange={(e) => setEnglish(e.target.value)} placeholder="English" required />
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)" />
        <button className="primary" disabled={saving}>
          {card ? "Save" : "Add"}
        </button>
        {card && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      {multiVowelWithoutStress && (
        <small className="stress-hint">
          Tip: add + before the stressed vowel (e.g. <code>молок+о</code>) so the stress shows and scoring knows which
          vowels reduce.
        </small>
      )}
    </form>
  );
}
