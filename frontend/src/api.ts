export interface Phrase {
  id: number;
  category: string;
  text: string; // with '+' stress marks
  display: string; // with accent marks
  plain: string;
  translit: string;
  english: string;
  sounds_like?: string;
  note?: string;
}

export type LetterStatus = "good" | "close" | "wrong" | "silent" | "unscored";

export interface LetterResult {
  char: string;
  stressed: boolean;
  status: LetterStatus;
  heard_as: string | null;
  score: number | null; // 0–1 for scored letters
}

/** Russian text described by the backend: stress-marked, display form and transliteration. */
export interface Described {
  text: string;
  display: string;
  plain: string;
  translit: string;
}

export interface WordItem extends Described {
  english: string;
}

export interface AlphabetLetter {
  upper: string;
  lower: string;
  name: string;
  name_display: string;
  latin: string;
  kind: "vowel" | "consonant" | "sign";
  sound: string;
  tip?: string;
  false_friend?: string;
  confusable?: string[];
  syllables: Described[]; // listen-only
  examples: WordItem[]; // speaking drill words
}

export interface Lesson {
  id: number;
  title: string;
  intro: string;
  letters: string[]; // uppercase
  words: WordItem[];
}

export interface Alphabet {
  letters: AlphabetLetter[];
  lessons: Lesson[];
}

export interface LetterMastery {
  count: number;
  average: number;
  status: "learning" | "mastered";
}

export type AttemptSource = "phrase" | "letter" | "reading" | "custom" | "flashcard";

export interface DeckCounts {
  total: number;
  new: number;
  learning: number;
  review: number;
  due: number;
  suspended: number;
}

export interface Deck {
  id: number;
  name: string;
  description: string;
  builtin: boolean;
  counts: DeckCounts;
}

export interface FlashCard extends Described {
  id: number;
  deck_id: number;
  english: string;
  notes: string;
  tag: string;
  suspended: boolean;
  state: "new" | "learning" | "review";
  due: number | null; // unix seconds
  is_due: boolean;
  reps: number;
  lapses: number;
  needs_stress: boolean;
  builtin: boolean;
}

export type RatingName = "again" | "hard" | "good" | "easy";

export interface Remaining {
  due: number;
  new: number;
}

export interface StudyNext {
  next: { card: FlashCard; kind: "new" | "review"; intervals: Record<RatingName, string>; remaining: Remaining } | null;
  remaining: Remaining;
}

export interface StudyStats extends Remaining {
  reviewed_today: number;
  average_score_today: number | null;
  streak_days: number;
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  return fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then((r) => json<T>(r));
}

export interface WordResult {
  text: string; // with '+' stress marks
  display: string;
  score: number;
  status: "good" | "close" | "wrong" | "missing";
  letters: LetterResult[];
  heard: string | null; // what speech recognition heard in this word's place
  recognized: "correct" | "close" | "wrong" | "missing";
}

export interface AttemptResult {
  heard: string;
  words: WordResult[];
  extra: string[];
  score: number;
  tips: string[];
}

export interface Health {
  tts: string;
  asr_loaded: boolean;
  asr_model: string;
  pronunciation_loaded: boolean;
  ready: boolean;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  health: () => fetch("/api/health").then((r) => json<Health>(r)),
  phrases: () => fetch("/api/phrases").then((r) => json<Phrase[]>(r)),
  alphabet: () => fetch("/api/alphabet").then((r) => json<Alphabet>(r)),
  letterProgress: () =>
    fetch("/api/progress/letters").then((r) => json<Record<string, LetterMastery>>(r)),
  describe: (text: string) =>
    fetch(`/api/describe?text=${encodeURIComponent(text)}`).then((r) => json<Phrase>(r)),
  decks: () => fetch("/api/decks").then((r) => json<Deck[]>(r)),
  createDeck: (name: string, description = "") => send<Deck>("/api/decks", "POST", { name, description }),
  deleteDeck: (id: number) => send<{ ok: boolean }>(`/api/decks/${id}`, "DELETE"),
  cards: (deckId: number) => fetch(`/api/decks/${deckId}/cards`).then((r) => json<FlashCard[]>(r)),
  addCard: (deckId: number, card: { russian: string; english: string; notes: string }) =>
    send<FlashCard>(`/api/decks/${deckId}/cards`, "POST", card),
  updateCard: (id: number, card: { russian: string; english: string; notes: string; suspended: boolean }) =>
    send<FlashCard>(`/api/cards/${id}`, "PUT", card),
  deleteCard: (id: number) => send<{ ok: boolean }>(`/api/cards/${id}`, "DELETE"),
  importCsv: (deckId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`/api/decks/${deckId}/import`, { method: "POST", body: form }).then((r) =>
      json<{ added: number; skipped_duplicates: number; errors: string[] }>(r),
    );
  },
  studyNext: (deckId: number | null) =>
    fetch(`/api/study/next${deckId ? `?deck_id=${deckId}` : ""}`).then((r) => json<StudyNext>(r)),
  rate: (cardId: number, rating: 1 | 2 | 3 | 4, score: number | null) =>
    send<{ card: FlashCard; next_due_in: string }>(`/api/study/${cardId}/rate`, "POST", { rating, score }),
  studyStats: () => fetch("/api/study/stats").then((r) => json<StudyStats>(r)),
  settings: () => fetch("/api/settings").then((r) => json<{ new_per_day: number }>(r)),
  updateSettings: (newPerDay: number) =>
    send<{ new_per_day: number }>("/api/settings", "PUT", { new_per_day: newPerDay }),
  ttsUrl: (text: string, speed: "normal" | "slow") =>
    `/api/tts?text=${encodeURIComponent(text)}&speed=${speed}`,
  attempt: (target: string, audio: Blob, source: AttemptSource) => {
    const form = new FormData();
    form.append("target", target);
    form.append("source", source);
    form.append("audio", audio, "attempt");
    return fetch("/api/attempt", { method: "POST", body: form }).then((r) => json<AttemptResult>(r));
  },
};
