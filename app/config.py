"""Central configuration.

Every hardware-dependent / deployment knob lives here and is read from the
environment (or a local .env). Nothing is hardcoded in the pipeline — the same
image runs on a GPU-less laptop (dev) and on the 4 GB-VRAM target PC (prod);
only the values differ. See .env.dev.example / .env.prod.example.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- HTTP / WS server ----
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # ---- LLM: Ollama (native on host, uses the GPU) ----
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_num_ctx: int = 4096
    ollama_temperature: float = 0.8
    ollama_keep_alive: str = "10m"
    # None => let Ollama auto-detect GPU layers. Set an int to cap for low VRAM.
    ollama_num_gpu: Optional[int] = None
    ollama_request_timeout: float = 180.0
    # Hard cap on reply length (num_predict). Conversation stays laconic; explain
    # gets more room for the rule + examples. Lower these for even shorter replies.
    reply_max_tokens_conversation: int = 80
    reply_max_tokens_explain: int = 320

    # ---- STT: faster-whisper (always CPU) ----
    whisper_model: str = "base"          # tiny | base | small | medium | ...
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_beam_size: int = 1
    stt_vad_filter: bool = True          # Silero VAD, bundled in faster-whisper
    stt_cpu_threads: int = 4
    whisper_download_root: str = "/app/models/whisper"

    # ---- TTS: Piper (always CPU) ----
    tts_backend: str = "piper"           # piper | kokoro (kokoro = future stub)
    tts_voice: str = "en_US-lessac-medium"      # voice for English replies
    tts_voice_ru: str = "ru_RU-irina-medium"    # voice for Russian replies
    tts_speaker_id: Optional[int] = None
    piper_data_dir: str = "/app/models/piper"
    # Kokoro backend (TTS_BACKEND=kokoro): natural English on CPU/onnxruntime.
    # Russian falls back to Piper (TTS_VOICE_RU). See VOICES.md for voice names.
    kokoro_voice: str = "af_heart"
    kokoro_lang: str = "en-us"
    kokoro_speed: float = 1.0
    kokoro_data_dir: str = "/app/models/kokoro"

    # ---- App behaviour ----
    default_input_lang: str = "en"       # en | ru  (Whisper language)
    default_mode: str = "conversation"   # conversation | explain
    db_path: str = "/app/data/progress.db"
    syllabus_path: str = "/app/syllabus.yaml"
    history_max_messages: int = 12       # rolling chat history cap sent to LLM

    def tts_voice_for(self, lang: str) -> str:
        """Pick the Piper voice that matches the response language."""
        return self.tts_voice_ru if lang.lower().startswith("ru") else self.tts_voice

    def max_tokens_for(self, mode: str) -> int:
        """Reply length cap (num_predict) for the given mode."""
        return self.reply_max_tokens_explain if mode == "explain" else self.reply_max_tokens_conversation


@lru_cache
def get_settings() -> Settings:
    return Settings()
