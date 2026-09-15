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
MERGE_GAP_FRAMES = 12    # quiet stretches up to 240 ms (e.g. a stop consonant's closure) stay inside the speech
MIN_SPEECH_FRAMES = 5    # a loud stretch shorter than 100 ms, set apart from the speech, is a click


def voiced_bounds(audio: np.ndarray) -> tuple[int, int] | None:
    """Sample range from the start to the end of speech.

    Short isolated bursts before or after the speech, such as the key press that started or stopped the
    recording, are left out.
    """
    n = audio.size // FRAME
    if n == 0:
        return None
    rms = np.sqrt(np.mean(audio[: n * FRAME].reshape(n, FRAME) ** 2, axis=1))
    threshold = max(0.01, rms.max() * 0.08)
    voiced = np.where(rms > threshold)[0]
    if not voiced.size:
        return None

    runs: list[list[int]] = [[voiced[0], voiced[0], 1]]  # [first frame, last frame, voiced frame count]
    for f in voiced[1:]:
        if f - runs[-1][1] <= MERGE_GAP_FRAMES:
            runs[-1][1] = f
            runs[-1][2] += 1
        else:
            runs.append([f, f, 1])
    speech = [r for r in runs if r[2] >= MIN_SPEECH_FRAMES] or runs
    return int(speech[0][0] * FRAME), int((speech[-1][1] + 1) * FRAME)


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
