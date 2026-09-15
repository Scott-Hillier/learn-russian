import { useEffect, useMemo, useRef } from "react";

/** A single shared audio player per component: playing something new stops what was playing. */
export function useAudio(onError?: (message: string) => void) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const player = useMemo(
    () => ({
      /** `quiet`: don't report failures (automatic playback the browser may block before any click). */
      play(src: string, { quiet = false } = {}) {
        ref.current ??= new Audio();
        const a = ref.current;
        a.pause();
        a.src = src;
        a.play().catch(() => quiet || onErrorRef.current?.("Couldn't play audio."));
      },
      stop() {
        ref.current?.pause();
      },
    }),
    [],
  );

  useEffect(() => () => ref.current?.pause(), []);
  return player;
}
