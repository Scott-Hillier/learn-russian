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


def trim_and_pad(audio: np.ndarray, pad_s: float = 0.3) -> np.ndarray:
    """Trim leading/trailing silence, then pad a little so Whisper doesn't clip short words."""
    if audio.size == 0:
        return audio
    frame = int(0.02 * SAMPLE_RATE)
    n = audio.size // frame
    if n == 0:
        return audio
    rms = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1))
    threshold = max(0.01, rms.max() * 0.08)
    voiced = np.where(rms > threshold)[0]
    if voiced.size:
        start = max(0, (voiced[0] - 5) * frame)
        end = min(audio.size, (voiced[-1] + 6) * frame)
        audio = audio[start:end]
    pad = np.zeros(int(pad_s * SAMPLE_RATE), dtype=np.float32)
    return np.concatenate([pad, audio, pad])


def peak_level(audio: np.ndarray) -> float:
    return float(np.abs(audio).max()) if audio.size else 0.0
