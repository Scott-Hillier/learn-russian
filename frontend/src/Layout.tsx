import type { ReactNode } from "react";
import type { Health } from "./api";
import Stressed from "./Stressed";

export type Mode = "alphabet" | "flashcards" | "sentences" | "pairs" | "phrases";

const MODES: { id: Mode; label: string }[] = [
  { id: "alphabet", label: "🔤 Letters & Sounds" },
  { id: "flashcards", label: "🃏 Flashcards" },
  { id: "sentences", label: "🗣 Sentences" },
  { id: "pairs", label: "👂 Sound pairs" },
  { id: "phrases", label: "💬 Phrases" },
];

interface Props {
  mode: Mode;
  onMode: (mode: Mode) => void;
  health: Health | null;
  sidebar: ReactNode;
  children: ReactNode;
}

export default function Layout({ mode, onMode, health, sidebar, children }: Props) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>
          <Stressed text="Говори́!" /> <small>Speak Russian</small>
        </h1>
        <nav className="modes">
          {MODES.map((m) => (
            <button key={m.id} className={mode === m.id ? "active" : ""} onClick={() => onMode(m.id)}>
              {m.label}
            </button>
          ))}
        </nav>
        {sidebar}
      </aside>

      <main>
        {health && !health.ready && (
          <div className="banner">Loading speech models… (first start can take a minute)</div>
        )}
        {children}
        <footer>
          {health ? `Voice: ${health.tts} · Recognition: ${health.asr_model.split("/").pop()}` : "Connecting…"}
          {" · "}Shortcuts: <kbd>L</kbd> listen <kbd>S</kbd> slow <kbd>Space</kbd> record <kbd>←</kbd>
          <kbd>→</kbd> next/previous
        </footer>
      </main>
    </div>
  );
}
