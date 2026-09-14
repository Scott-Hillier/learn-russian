import { useEffect, useMemo, useRef } from "react";

/** A single shared audio player per component: playing something new stops what was playing. */
export function useAudio(onError?: (message: string) => void) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const player = useMemo(
    () => ({
      play(src: string) {
        ref.current ??= new Audio();
        const a = ref.current;
        a.pause();
        a.src = src;
        a.play().catch(() => onErrorRef.current?.("Couldn't play audio."));
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
