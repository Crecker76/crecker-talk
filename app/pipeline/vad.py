"""Voice Activity Detection.

We use the Silero VAD that ships *inside* faster-whisper, enabled via
``vad_filter=True`` in :meth:`app.pipeline.stt.STT.transcribe`. That keeps the
image lean (no torch) while still getting Silero-quality VAD on CPU.

With push-to-talk the user already gates recording with Space; the VAD then
trims leading/trailing silence and drops pure-noise clips so Whisper doesn't
hallucinate text on them.
"""

from __future__ import annotations

from ..config import Settings


def vad_enabled(settings: Settings) -> bool:
    return settings.stt_vad_filter


def vad_parameters() -> dict:
    # Tuned for short push-to-talk utterances.
    return {"min_silence_duration_ms": 300}
