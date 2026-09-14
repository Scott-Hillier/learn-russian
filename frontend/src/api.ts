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

export type WordStatus = "correct" | "close" | "wrong" | "missing";

export interface AttemptResult {
  heard: string;
  words: { target: string; heard: string | null; status: WordStatus }[];
  extra: string[];
  score: number;
  tips: string[];
}

export interface Health {
  tts: string;
  asr_loaded: boolean;
  asr_model: string;
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
  describe: (text: string) =>
    fetch(`/api/describe?text=${encodeURIComponent(text)}`).then((r) => json<Phrase>(r)),
  ttsUrl: (text: string, speed: "normal" | "slow") =>
    `/api/tts?text=${encodeURIComponent(text)}&speed=${speed}`,
  attempt: (target: string, audio: Blob) => {
    const form = new FormData();
    form.append("target", target);
    form.append("audio", audio, "attempt");
    return fetch("/api/attempt", { method: "POST", body: form }).then((r) => json<AttemptResult>(r));
  },
};
