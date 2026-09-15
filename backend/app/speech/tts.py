"""Text-to-speech: Silero v4 Russian (offline after first download), macOS `say` fallback."""
import hashlib
import logging
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from .. import config
from ..text import expand_numbers, strip_stress

log = logging.getLogger(__name__)

SPEEDS = {"normal": None, "slow": "slow", "x-slow": "x-slow"}
_SAY_RATES = {"normal": 170, "slow": 120, "x-slow": 90}


class TTS:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self.engine = "not loaded"

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                import torch

                if not config.SILERO_PATH.exists():
                    log.info("Downloading Silero TTS model (one-time)…")
                    _download(config.SILERO_URL, config.SILERO_PATH)
                torch.set_num_threads(4)
                model = torch.package.PackageImporter(str(config.SILERO_PATH)).load_pickle("tts_models", "model")
                model.to(torch.device("cpu"))
                self._model = model
                self.engine = f"silero ({config.TTS_SPEAKER})"
            except Exception:
                log.exception("Silero TTS unavailable, falling back to macOS 'say'")
                self._model = False
                self.engine = "macOS say (Milena)"

    def synthesize(self, text: str, speed: str = "normal") -> Path:
        """Return path to a cached WAV file for `text` (may contain '+' stress marks)."""
        if speed not in SPEEDS:
            speed = "normal"
        text = expand_numbers(text)  # Silero has no number normaliser and silently drops digits
        self.load()
        key = hashlib.sha1(f"{self.engine}|{speed}|{text}".encode()).hexdigest()
        out = config.TTS_CACHE_DIR / f"{key}.wav"
        if out.exists():
            return out
        if self._model:
            self._silero(text, speed, out)
        else:
            self._say(text, speed, out)
        return out

    def _silero(self, text: str, speed: str, out: Path) -> None:
        import soundfile as sf

        kwargs = dict(speaker=config.TTS_SPEAKER, sample_rate=config.TTS_SAMPLE_RATE,
                      put_accent=True, put_yo=True)
        rate = SPEEDS[speed]
        with self._lock:
            if rate:
                ssml = f"<speak><prosody rate=\"{rate}\">{escape(text)}</prosody></speak>"
                audio = self._model.apply_tts(ssml_text=ssml, **kwargs)
            else:
                audio = self._model.apply_tts(text=text, **kwargs)
        sf.write(out, audio.numpy(), config.TTS_SAMPLE_RATE)

    def _say(self, text: str, speed: str, out: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "say.aiff"
            subprocess.run(["say", "-v", "Milena", "-r", str(_SAY_RATES[speed]), "-o", str(aiff),
                            strip_stress(text)], check=True)
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(aiff), str(out)],
                           check=True)


def _download(url: str, dest: Path) -> None:
    import shutil
    import ssl

    import certifi  # python.org builds of Python ship without system CA certificates

    ctx = ssl.create_default_context(cafile=certifi.where())
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, context=ctx) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.rename(dest)


tts = TTS()
