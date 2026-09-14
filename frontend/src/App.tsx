import { useEffect, useState } from "react";
import { api, type Health } from "./api";
import AlphabetView from "./AlphabetView";
import ConversationView from "./ConversationView";
import FlashcardsView from "./FlashcardsView";
import type { Mode } from "./Layout";
import PairsView from "./PairsView";
import PhrasesView from "./PhrasesView";
import ProgressView from "./ProgressView";
import SentencesView from "./SentencesView";

const MODE_KEY = "learn-russian:mode";
const MODES: Mode[] = ["alphabet", "flashcards", "sentences", "pairs", "conversation", "phrases", "progress"];

function loadMode(): Mode {
  try {
    const stored = localStorage.getItem(MODE_KEY) as Mode | null;
    return stored && MODES.includes(stored) ? stored : "alphabet";
  } catch {
    return "alphabet";
  }
}

export default function App() {
  const [mode, setMode] = useState<Mode>(loadMode);
  const [health, setHealth] = useState<Health | null>(null);

  const changeMode = (m: Mode) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      /* storage unavailable: mode just isn't remembered */
    }
  };

  // Poll until the speech models have finished loading.
  useEffect(() => {
    let timer: number;
    const poll = () =>
      api
        .health()
        .then((h) => {
          setHealth(h);
          if (!h.ready) timer = window.setTimeout(poll, 2000);
        })
        .catch(() => (timer = window.setTimeout(poll, 3000)));
    poll();
    return () => clearTimeout(timer);
  }, []);

  const layout = { mode, onMode: changeMode, health };
  if (mode === "flashcards") return <FlashcardsView layout={layout} />;
  if (mode === "sentences") return <SentencesView layout={layout} />;
  if (mode === "pairs") return <PairsView layout={layout} />;
  if (mode === "conversation") return <ConversationView layout={layout} />;
  if (mode === "phrases") return <PhrasesView layout={layout} />;
  if (mode === "progress") return <ProgressView layout={layout} />;
  return <AlphabetView layout={layout} />;
}
