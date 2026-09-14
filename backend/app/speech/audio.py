import subprocess

import numpy as np

SAMPLE_RATE = 16000


def decode_to_pcm16k(data: bytes) -> np.ndarray:
    """Decode any browser audio (webm/opus, ogg, mp4, wav) to mono float32 at 16 kHz."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
        input=data, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"Could not decode audio: {proc.stderr.decode(errors='ignore').strip()}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


FRAME = int(0.02 * SAMPLE_RATE)


def voiced_bounds(audio: np.ndarray) -> tuple[int, int] | None:
    """Sample range from the first to the last frame loud enough to be speech."""
    n = audio.size // FRAME
    if n == 0:
        return None
    rms = np.sqrt(np.mean(audio[: n * FRAME].reshape(n, FRAME) ** 2, axis=1))
    threshold = max(0.01, rms.max() * 0.08)
    voiced = np.where(rms > threshold)[0]
    if not voiced.size:
        return None
    return int(voiced[0] * FRAME), int((voiced[-1] + 1) * FRAME)


def voiced_duration(audio: np.ndarray) -> float:
    """Seconds between the start and end of speech (pauses inside the utterance included)."""
    bounds = voiced_bounds(audio)
    return (bounds[1] - bounds[0]) / SAMPLE_RATE if bounds else 0.0


def trim_and_pad(audio: np.ndarray, pad_s: float = 0.3) -> np.ndarray:
    """Trim leading/trailing silence, then pad a little so Whisper doesn't clip short words."""
    bounds = voiced_bounds(audio)
    if bounds:
        start = max(0, bounds[0] - 5 * FRAME)
        end = min(audio.size, bounds[1] + 5 * FRAME)
        audio = audio[start:end]
    pad = np.zeros(int(pad_s * SAMPLE_RATE), dtype=np.float32)
    return np.concatenate([pad, audio, pad])


def peak_level(audio: np.ndarray) -> float:
    return float(np.abs(audio).max()) if audio.size else 0.0
