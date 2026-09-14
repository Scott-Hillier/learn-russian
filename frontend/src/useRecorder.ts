import { useCallback, useEffect, useRef, useState } from "react";

const SPEECH_LEVEL = 0.06; // RMS above this counts as speaking
const SILENCE_STOP_MS = 1400; // auto-stop after this much silence once speech started
const MAX_MS = 15000;

/** Microphone recorder with a live level meter and auto-stop on silence. */
export function useRecorder(onDone: (audio: Blob) => void) {
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const rafRef = useRef<number>(0);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
    setLevel(0);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      if (!streamRef.current) {
        streamRef.current = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        });
      }
    } catch {
      setError("Microphone access was blocked. Allow it in your browser's site settings.");
      return;
    }
    const stream = streamRef.current;
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      ctx.close();
      onDoneRef.current(new Blob(chunks, { type: recorder.mimeType }));
    };
    recorderRef.current = recorder;

    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const startedAt = performance.now();
    let heardSpeech = false;
    let lastLoud = startedAt;

    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length);
      setLevel(Math.min(1, rms * 6));
      const now = performance.now();
      if (rms > SPEECH_LEVEL) {
        heardSpeech = true;
        lastLoud = now;
      }
      if ((heardSpeech && now - lastLoud > SILENCE_STOP_MS) || now - startedAt > MAX_MS) {
        stop();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    recorder.start();
    setRecording(true);
    rafRef.current = requestAnimationFrame(tick);
  }, [stop]);

  useEffect(
    () => () => {
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  return { recording, level, error, start, stop };
}
