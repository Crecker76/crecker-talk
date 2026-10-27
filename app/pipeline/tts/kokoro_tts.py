"""Kokoro TTS backend — natural English voice on CPU (onnxruntime, no torch).

Kokoro handles English; Russian falls back to Piper (Kokoro has no Russian).
Model files are downloaded on first use into KOKORO_DATA_DIR.
"""

from __future__ import annotations

import io
import logging
import threading
import urllib.request
import wave
from pathlib import Path

import numpy as np

from ...config import Settings
from .base import TTSBackend
from .piper_tts import PiperBackend

logger = logging.getLogger("vet.tts.kokoro")

_REL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
MODEL_URL = f"{_REL}/kokoro-v1.0.onnx"
VOICES_URL = f"{_REL}/voices-v1.0.bin"


class KokoroBackend(TTSBackend):
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._kokoro = None
        self._lock = threading.Lock()
        self._piper = PiperBackend(settings)  # Russian (and any non-English) fallback
        Path(self.s.kokoro_data_dir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        logger.info("Downloading Kokoro file: %s", url)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "voice-english-trainer"})
        with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:  # noqa: S310
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        tmp.replace(dest)

    def _ensure_kokoro(self):
        if self._kokoro is not None:
            return self._kokoro
        with self._lock:
            if self._kokoro is not None:
                return self._kokoro
            data = Path(self.s.kokoro_data_dir)
            model = data / "kokoro-v1.0.onnx"
            voices = data / "voices-v1.0.bin"
            if not model.exists():
                self._download(MODEL_URL, model)
            if not voices.exists():
                self._download(VOICES_URL, voices)
            from kokoro_onnx import Kokoro

            logger.info("Loading Kokoro model (%s)", self.s.kokoro_voice)
            self._kokoro = Kokoro(str(model), str(voices))
            return self._kokoro

    def synthesize(self, text: str, lang: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        if lang.lower().startswith("ru"):
            return self._piper.synthesize(text, "ru")

        kokoro = self._ensure_kokoro()
        samples, sample_rate = kokoro.create(
            text, voice=self.s.kokoro_voice, speed=self.s.kokoro_speed, lang=self.s.kokoro_lang
        )
        audio = np.asarray(samples, dtype=np.float32)
        pcm16 = np.clip(audio * 32767.0, -32768, 32767).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(sample_rate))
            wav.writeframes(pcm16)
        return buf.getvalue()

    def warmup(self, lang: str = "en") -> None:
        if lang.lower().startswith("ru"):
            self._piper.warmup("ru")
        else:
            self._ensure_kokoro()
