import { useCallback, useEffect, useState } from "react";

const CHANGED = "learn-russian:pref-changed";

function read(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(`learn-russian:${key}`);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

/** A boolean preference remembered in this browser and kept in sync across components. */
export function usePref(key: string, fallback: boolean) {
  const [value, setValue] = useState(() => read(key, fallback));

  useEffect(() => {
    const sync = () => setValue(read(key, fallback));
    window.addEventListener(CHANGED, sync);
    return () => window.removeEventListener(CHANGED, sync);
  }, [key, fallback]);

  const set = useCallback(
    (v: boolean) => {
      try {
        localStorage.setItem(`learn-russian:${key}`, v ? "1" : "0");
      } catch {
        /* storage unavailable: the choice lasts until reload */
      }
      setValue(v);
      window.dispatchEvent(new Event(CHANGED));
    },
    [key],
  );

  return [value, set] as const;
}
