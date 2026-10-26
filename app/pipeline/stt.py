"""Speech-to-text via faster-whisper (always CPU).

Accepts raw encoded audio bytes (webm/opus/ogg/wav from the browser). Decoding
is handled by faster-whisper through PyAV (bundled ffmpeg), so no system ffmpeg
is required. The Whisper `language` is passed straight from the UI switch.
"""

from __future__ import annotations

import io
import logging
import threading

from ..config import Settings
from . import vad

logger = logging.getLogger("vet.stt")


class STT:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    logger.info(
                        "Loading faster-whisper model=%s device=%s compute=%s",
                        self.settings.whisper_model,
                        self.settings.stt_device,
                        self.settings.stt_compute_type,
                    )
                    self._model = WhisperModel(
                        self.settings.whisper_model,
                        device=self.settings.stt_device,
                        compute_type=self.settings.stt_compute_type,
                        cpu_threads=self.settings.stt_cpu_threads,
                        download_root=self.settings.whisper_download_root,
                    )
        return self._model

    def warmup(self) -> None:
        self._ensure_model()

    def transcribe(self, audio: bytes, language: str) -> str:
        """Blocking transcription; call via asyncio.to_thread()."""
        model = self._ensure_model()
        lang = language if language in ("en", "ru") else None
        segments, _info = model.transcribe(
            io.BytesIO(audio),
            language=lang,
            beam_size=self.settings.stt_beam_size,
            vad_filter=vad.vad_enabled(self.settings),
            vad_parameters=vad.vad_parameters() if vad.vad_enabled(self.settings) else None,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info("STT(%s) -> %r", language, text)
        return text
