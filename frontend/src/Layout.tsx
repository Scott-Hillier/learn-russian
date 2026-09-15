import { useEffect, useRef, type ReactNode } from "react";
import type { Health } from "./api";
import Stressed from "./Stressed";

export type Mode = "alphabet" | "flashcards" | "sentences" | "pairs" | "conversation" | "phrases" | "progress";

const MODES: { id: Mode; label: string }[] = [
  { id: "alphabet", label: "🔤 Letters & Sounds" },
  { id: "flashcards", label: "🃏 Flashcards" },
  { id: "sentences", label: "🗣 Sentences" },
  { id: "pairs", label: "👂 Sound pairs" },
  { id: "conversation", label: "🤖 Conversation" },
  { id: "phrases", label: "💬 Phrases" },
  { id: "progress", label: "📈 Progress" },
];

interface Props {
  mode: Mode;
  onMode: (mode: Mode) => void;
  health: Health | null;
  sidebar: ReactNode;
  children: ReactNode;
}

export default function Layout({ mode, onMode, health, sidebar, children }: Props) {
  const sidebarRef = useRef<HTMLElement>(null);
  const lastActive = useRef<Element | null>(null);

  // Keep the selected item visible in the sidebar list as Next/Back moves through it.
  useEffect(() => {
    const aside = sidebarRef.current;
    const active = aside?.querySelector("ul .active");
    if (!aside || !active || active === lastActive.current) return;
    lastActive.current = active;
    const a = active.getBoundingClientRect();
    const box = aside.getBoundingClientRect();
    if (a.top < box.top) aside.scrollTop -= box.top - a.top + 12;
    else if (a.bottom > box.bottom) aside.scrollTop += a.bottom - box.bottom + 12;
  });

  return (
    <div className="layout">
      <aside className="sidebar" ref={sidebarRef}>
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
        </footer>
      </main>
    </div>
  );
}
