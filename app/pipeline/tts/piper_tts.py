"""Piper TTS backend (CPU, self-contained).

Voices are downloaded on first use from the official rhasspy/piper-voices HF
repo into ``PIPER_DATA_DIR`` (a mounted volume) and cached in memory.
Voice name format: ``<lang>_<REGION>-<name>-<quality>`` e.g. ``en_US-lessac-medium``.
"""

from __future__ import annotations

import io
import logging
import threading
import urllib.request
import wave
from pathlib import Path
from typing import Dict, Tuple

from ...config import Settings
from .base import TTSBackend

logger = logging.getLogger("vet.tts.piper")

VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _voice_rel_path(voice: str) -> str:
    # en_US-lessac-medium -> en/en_US/lessac/medium/en_US-lessac-medium
    parts = voice.split("-")
    if len(parts) < 3:
        raise ValueError(f"Unexpected Piper voice name: {voice!r}")
    locale = parts[0]                 # en_US
    name = parts[1]                   # lessac
    quality = "-".join(parts[2:])     # medium (or x_low style, defensive)
    lang = locale.split("_")[0]       # en
    return f"{lang}/{locale}/{name}/{quality}/{voice}"


class PiperBackend(TTSBackend):
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._voices: Dict[str, object] = {}  # voice_name -> PiperVoice
        self._lock = threading.Lock()
        Path(self.s.piper_data_dir).mkdir(parents=True, exist_ok=True)

    # ---- model files ----
    def _ensure_files(self, voice: str) -> Tuple[Path, Path]:
        data_dir = Path(self.s.piper_data_dir)
        onnx = data_dir / f"{voice}.onnx"
        conf = data_dir / f"{voice}.onnx.json"
        if onnx.exists() and conf.exists():
            return onnx, conf
        rel = _voice_rel_path(voice)
        self._download(f"{VOICE_BASE_URL}/{rel}.onnx", onnx)
        self._download(f"{VOICE_BASE_URL}/{rel}.onnx.json", conf)
        return onnx, conf

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        logger.info("Downloading Piper voice file: %s", url)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "voice-english-trainer"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:  # noqa: S310
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        tmp.replace(dest)

    # ---- voice cache ----
    def _ensure_voice(self, lang: str):
        voice_name = self.s.tts_voice_for(lang)
        cached = self._voices.get(voice_name)
        if cached is not None:
            return cached
        with self._lock:
            cached = self._voices.get(voice_name)
            if cached is not None:
                return cached
            from piper import PiperVoice

            onnx, conf = self._ensure_files(voice_name)
            logger.info("Loading Piper voice %s", voice_name)
            voice = PiperVoice.load(str(onnx), config_path=str(conf))
            self._voices[voice_name] = voice
            return voice

    # ---- synthesis ----
    def synthesize(self, text: str, lang: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        voice = self._ensure_voice(lang)
        sample_rate = int(voice.config.sample_rate)

        pcm = bytearray()
        for chunk in voice.synthesize_stream_raw(text, speaker_id=self.s.tts_speaker_id):
            pcm.extend(chunk)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # int16
            wav.setframerate(sample_rate)
            wav.writeframes(bytes(pcm))
        return buf.getvalue()

    def warmup(self, lang: str = "en") -> None:
        self._ensure_voice(lang)
