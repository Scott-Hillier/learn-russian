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

export type AttemptSource = "phrase" | "letter" | "reading" | "custom";

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
