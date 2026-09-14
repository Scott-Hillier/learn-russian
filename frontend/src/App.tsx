import { useEffect, useState } from "react";
import { api, type Health } from "./api";
import AlphabetView from "./AlphabetView";
import type { Mode } from "./Layout";
import PhrasesView from "./PhrasesView";

const MODE_KEY = "learn-russian:mode";

function loadMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === "phrases" ? "phrases" : "alphabet";
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
  return mode === "alphabet" ? <AlphabetView layout={layout} /> : <PhrasesView layout={layout} />;
}
