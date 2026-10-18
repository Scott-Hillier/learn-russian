"""Keep the learner's latest attempts on disk (audio + feedback), to check how scoring treats their voice.

Only active when the app is started with SAVE_RECORDINGS=1 (see config.SAVE_RECORDINGS).
"""
import json
import logging
import time

from . import config

log = logging.getLogger(__name__)


def save(target: str, data: bytes, feedback: dict) -> None:
    """Keep the latest attempts on disk (see config.SAVE_RECORDINGS)."""
    try:
        config.RECORDINGS_DIR.mkdir(exist_ok=True)
        now = time.time()
        stem = config.RECORDINGS_DIR / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}-{int(now * 1000) % 1000:03d}"
        stem.with_suffix(".webm").write_bytes(data)
        stem.with_suffix(".json").write_text(json.dumps({"target": target, "feedback": feedback}, ensure_ascii=False))
        for old in sorted(config.RECORDINGS_DIR.glob("*.webm"))[:-config.RECORDINGS_KEPT]:
            old.unlink()
            old.with_suffix(".json").unlink(missing_ok=True)
    except Exception:
        log.exception("Could not save recording")
