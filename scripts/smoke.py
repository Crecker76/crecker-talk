"""Offline smoke test: Piper TTS -> faster-whisper STT round trip.

No LLM, no microphone. Verifies the two CPU legs of the pipeline end to end:
Piper synthesizes a phrase to WAV, faster-whisper transcribes it back.

Run inside the container:
    docker compose run --rm app python scripts/smoke.py
"""

from __future__ import annotations

import os
import sys

# Make `app` importable whether run as `python scripts/smoke.py` or `-m scripts.smoke`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.pipeline.stt import STT  # noqa: E402
from app.pipeline.tts import get_tts_backend  # noqa: E402


def main() -> int:
    s = get_settings()
    tts = get_tts_backend(s)
    stt = STT(s)

    phrase = "Hello, this is a quick microphone test."
    print(f"[TTS] voice={s.tts_voice!r} text={phrase!r}")
    wav = tts.synthesize(phrase, "en")
    print(f"[TTS] produced WAV bytes: {len(wav)}")
    if len(wav) < 1000:
        print("FAIL: TTS produced no audio")
        return 1

    print(f"[STT] model={s.whisper_model!r} transcribing…")
    heard = stt.transcribe(wav, "en")
    print(f"[STT] heard: {heard!r}")

    ok = any(word in heard.lower() for word in ("hello", "microphone", "test"))
    print(f"ROUNDTRIP_OK: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
