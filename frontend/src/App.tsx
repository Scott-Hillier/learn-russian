import { useEffect, useState } from "react";
import { api, type CourseNext, type Health } from "./api";
import AlphabetView from "./AlphabetView";
import ConversationView from "./ConversationView";
import CourseView from "./CourseView";
import FlashcardsView from "./FlashcardsView";
import HomeView from "./HomeView";
import type { Mode } from "./Layout";
import PairsView from "./PairsView";
import PhrasesView from "./PhrasesView";
import ProgressView from "./ProgressView";
import SentencesView from "./SentencesView";

const MODE_KEY = "learn-russian:mode";
const MODES: Mode[] = ["home", "course", "alphabet", "flashcards", "sentences", "pairs", "conversation", "phrases", "progress"];

function loadMode(): Mode {
  try {
    const stored = localStorage.getItem(MODE_KEY) as Mode | null;
    return stored && MODES.includes(stored) ? stored : "home";
  } catch {
    return "home";
  }
}

export default function App() {
  const [mode, setMode] = useState<Mode>(loadMode);
  const [health, setHealth] = useState<Health | null>(null);
  const [start, setStart] = useState<CourseNext | null>(null); // open and start this on the Lessons screen

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

  // A page left open across an update keeps running the old code against the new server. Check whenever the
  // window comes back into focus (and every few minutes) and offer a reload.
  const outdated = useOutdated();

  const layout = { mode, onMode: changeMode, health };
  const view =
    mode === "flashcards" ? (
      <FlashcardsView layout={layout} />
    ) : mode === "sentences" ? (
      <SentencesView layout={layout} />
    ) : mode === "pairs" ? (
      <PairsView layout={layout} />
    ) : mode === "conversation" ? (
      <ConversationView layout={layout} />
    ) : mode === "phrases" ? (
      <PhrasesView layout={layout} />
    ) : mode === "progress" ? (
      <ProgressView layout={layout} />
    ) : mode === "alphabet" ? (
      <AlphabetView layout={layout} />
    ) : mode === "course" ? (
      <CourseView layout={layout} start={start} onStarted={() => setStart(null)} />
    ) : (
      <HomeView
        layout={layout}
        onStart={(next) => {
          setStart(next);
          changeMode("course");
        }}
      />
    );
  return (
    <>
      {outdated && (
        <div className="update-banner" role="alert">
          The app has been updated. Reload to use the new version (your progress is saved).
          <button className="primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )}
      {view}
    </>
  );
}

/** The script this page runs, e.g. "/assets/index-D263XKXu.js" (null in the dev server, which is never stale). */
const OWN_BUNDLE = (() => {
  const path = new URL(import.meta.url).pathname;
  return path.startsWith("/assets/") ? path : null;
})();

function useOutdated(): boolean {
  const [outdated, setOutdated] = useState(false);
  useEffect(() => {
    if (!OWN_BUNDLE) return;
    const check = () =>
      api
        .health()
        .then((h) => h.bundle && h.bundle !== OWN_BUNDLE && setOutdated(true))
        .catch(() => {});
    check();
    const timer = window.setInterval(check, 5 * 60_000);
    window.addEventListener("focus", check);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, []);
  return outdated;
}
