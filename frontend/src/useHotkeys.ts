import { useEffect, useRef } from "react";

/** Key names passed to handlers: "space", "enter", "arrowleft", "arrowright", or a lower-case letter/digit. */
type Handler = (key: string) => boolean | void;

const TEXT_INPUT = /^(text|search|email|number|password|url|tel)$/;

/** Physical key name, so shortcuts still work with a Russian keyboard layout (L is "д" there). */
function keyName(e: KeyboardEvent): string {
  if (e.code === "Space") return "space";
  const letter = /^Key([A-Z])$/.exec(e.code) ?? /^(?:Digit|Numpad)(\d)$/.exec(e.code);
  return letter ? letter[1].toLowerCase() : e.key.toLowerCase();
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  if (el.isContentEditable || el.tagName === "TEXTAREA" || el.tagName === "SELECT") return true;
  return el instanceof HTMLInputElement && TEXT_INPUT.test(el.type);
}

/**
 * Page-wide keyboard shortcuts. Ignored while typing in a field and when a modifier is held (so browser
 * shortcuts like ⌘L keep working). Return true from the handler when the key was used: its default
 * action, such as clicking the focused button or scrolling, is then prevented.
 */
export function useHotkeys(handler: Handler) {
  const ref = useRef(handler);
  ref.current = handler;

  useEffect(() => {
    const handled = new Set<string>();
    const onDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      const key = keyName(e);
      if (e.repeat) {
        // Holding a key shouldn't fire it again, nor fall through to scrolling or clicking.
        if (handled.has(key)) e.preventDefault();
        return;
      }
      if (ref.current(key)) {
        e.preventDefault();
        handled.add(key);
      } else handled.delete(key);
    };
    // Space activates a focused button on key up, so swallow that too.
    const onUp = (e: KeyboardEvent) => {
      if (e.code === "Space" && handled.has("space")) e.preventDefault();
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, []);
}
