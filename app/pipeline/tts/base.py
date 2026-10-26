"""TTS backend interface. Each backend returns a complete WAV per call."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TTSBackend(ABC):
    @abstractmethod
    def synthesize(self, text: str, lang: str) -> bytes:
        """Synthesize `text` in `lang` ('en'/'ru'); return WAV bytes (incl. header).

        Blocking — call via asyncio.to_thread(). `lang` selects the voice so the
        Russian 'explain' replies are spoken by a Russian voice.
        """

    def warmup(self, lang: str = "en") -> None:  # pragma: no cover - optional
        ...

    def close(self) -> None:  # pragma: no cover - optional
        ...
