import { useState } from "react";
import { api, type Deck } from "./api";

/** Copy cards into another deck and describe what happened, e.g. "Added 3 words to Tricky words." */
export async function copyToDeck(deck: Deck, cardIds: number[]): Promise<string> {
  const r = await api.copyCards(deck.id, cardIds);
  const parts = [`Added ${r.added} word${r.added === 1 ? "" : "s"} to ${deck.name}`];
  if (r.skipped_duplicates) parts.push(`${r.skipped_duplicates} already there`);
  return parts.join(" · ");
}

interface Props {
  decks: Deck[];
  excludeDeckId?: number; // the deck you're looking at: you can't copy words into itself
  target: Deck | null;
  onTarget: (deck: Deck | null) => void;
  selected: number[];
  onCopied: (message: string) => void;
  onError: (message: string) => void;
  onDecksChanged: () => void;
  onClearSelection: () => void;
}

/** "Add to deck" toolbar: pick a deck (or make one), then add the ticked words to it. */
export default function AddToDeck({
  decks,
  excludeDeckId,
  target,
  onTarget,
  selected,
  onCopied,
  onError,
  onDecksChanged,
  onClearSelection,
}: Props) {
  const [newName, setNewName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const options = decks.filter((d) => d.id !== excludeDeckId);

  const createDeck = async () => {
    const name = (newName ?? "").trim();
    if (!name) return;
    setBusy(true);
    try {
      const deck = await api.createDeck(name);
      onTarget(deck);
      onDecksChanged();
      setNewName(null);
      onCopied(`Created the deck “${deck.name}”. Tick words and add them.`);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!target || !selected.length) return;
    setBusy(true);
    try {
      onCopied(await copyToDeck(target, selected));
      onClearSelection();
      onDecksChanged();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (newName !== null) {
    return (
      <form
        className="add-to-deck"
        onSubmit={(e) => {
          e.preventDefault();
          createDeck();
        }}
      >
        <input
          autoFocus
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New deck name, e.g. Words I can't remember"
          maxLength={80}
        />
        <button className="primary" disabled={busy || !newName.trim()}>
          Create deck
        </button>
        <button type="button" onClick={() => setNewName(null)}>
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div className="add-to-deck">
      <label>
        Add to
        <select
          value={target?.id ?? ""}
          onChange={(e) => {
            if (e.target.value === "new") setNewName("");
            else onTarget(options.find((d) => String(d.id) === e.target.value) ?? null);
          }}
        >
          <option value="">Choose a deck…</option>
          {options.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
          <option value="new">＋ New deck…</option>
        </select>
      </label>
      <button className="primary" onClick={add} disabled={busy || !target || !selected.length}>
        {selected.length ? `Add ${selected.length} word${selected.length === 1 ? "" : "s"}` : "Add"}
      </button>
      {selected.length > 0 && (
        <button type="button" onClick={onClearSelection}>
          Clear
        </button>
      )}
    </div>
  );
}
