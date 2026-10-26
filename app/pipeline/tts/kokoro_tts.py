"""Kokoro TTS backend — reserved optional backend for the future.

Not implemented yet (and intentionally not blocking on espeak-ng now). To make
it real later: add the kokoro dependency, load the model in __init__, and return
WAV bytes from synthesize() just like PiperBackend. Select it via TTS_BACKEND=kokoro.
"""

from __future__ import annotations

from ...config import Settings
from .base import TTSBackend


class KokoroBackend(TTSBackend):
    def __init__(self, settings: Settings) -> None:
        raise NotImplementedError(
            "TTS_BACKEND=kokoro is a reserved future backend and is not implemented. "
            "Use TTS_BACKEND=piper."
        )

    def synthesize(self, text: str, lang: str) -> bytes:  # pragma: no cover
        raise NotImplementedError
