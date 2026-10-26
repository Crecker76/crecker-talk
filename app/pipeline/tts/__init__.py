"""TTS backend factory."""

from __future__ import annotations

from ...config import Settings
from .base import TTSBackend


def get_tts_backend(settings: Settings) -> TTSBackend:
    backend = settings.tts_backend.lower()
    if backend == "piper":
        from .piper_tts import PiperBackend

        return PiperBackend(settings)
    if backend == "kokoro":
        from .kokoro_tts import KokoroBackend

        return KokoroBackend(settings)
    raise ValueError(f"Unknown TTS_BACKEND: {settings.tts_backend!r} (use 'piper' or 'kokoro')")
