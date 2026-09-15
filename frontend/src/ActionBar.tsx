import type { ReactNode } from "react";
import { usePref } from "./prefs";

interface Props {
  left?: ReactNode;
  center?: ReactNode;
  right?: ReactNode;
  /** Replaces the left/center/right slots, e.g. the flashcard rating buttons. */
  children?: ReactNode;
  /** Microphone level 0–1, drawn along the top edge while recording. */
  level?: number;
  hint?: ReactNode;
}

/**
 * Controls pinned to the bottom of the window, so Listen / Say it / Next stay in the same place from one
 * item to the next however long the feedback above them is.
 */
export default function ActionBar({ left, center, right, children, level, hint }: Props) {
  return (
    <div className="action-bar" role="toolbar">
      {level !== undefined && (
        <div className="action-meter" aria-hidden>
          <div style={{ width: `${level * 100}%` }} />
        </div>
      )}
      <div className="action-inner">
        {children ?? (
          <>
            <div className="action-side">{left}</div>
            <div className="action-center">{center}</div>
            <div className="action-side end">{right}</div>
          </>
        )}
      </div>
      {hint && <div className="action-hint">{hint}</div>}
    </div>
  );
}

/** Toggle for playing each new item's native audio automatically. */
export function AutoPlayToggle() {
  const [on, setOn] = usePref("autoplay", true);
  return (
    <button className="toggle" aria-pressed={on} onClick={() => setOn(!on)} title="Play each new item automatically">
      Auto-play {on ? "on" : "off"}
    </button>
  );
}
