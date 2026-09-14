"""Speech-to-text with mlx-whisper (Metal accelerated on Apple Silicon)."""
import threading

import numpy as np

from .. import config

# Whisper sometimes invents these on near-silent audio.
_HALLUCINATIONS = ("субтитры", "продолжение следует", "редактор субтитров", "спасибо за просмотр")


class ASR:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.loaded = False

    def warm_up(self) -> None:
        self.transcribe(np.zeros(16000, dtype=np.float32))
        self.loaded = True

    def transcribe(self, audio: np.ndarray) -> str:
        import mlx_whisper

        with self._lock:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=config.WHISPER_MODEL,
                language="ru",
                temperature=0.0,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                verbose=None,
            )
        self.loaded = True
        text = " ".join(seg["text"].strip() for seg in result.get("segments", [])).strip()
        if any(h in text.lower() for h in _HALLUCINATIONS):
            return ""
        return text


asr = ASR()
