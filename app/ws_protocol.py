"""WebSocket message vocabulary shared by backend and frontend.

Text frames are JSON objects with a ``type`` field. Binary frames sent by the
server are always WAV audio chunks (one per spoken clause); the browser decodes
them with the Web Audio API and plays them back in order.
"""

from __future__ import annotations

from typing import Any, Dict

# ---- character / pipeline states ----
STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"

# ---- server -> client message types ----
SERVER_STATE = "state"
SERVER_TRANSCRIPT = "transcript"   # what STT heard (the user's turn)
SERVER_LLM_TEXT = "llm_text"       # streamed assistant text
SERVER_MODE = "mode"               # current mode + response language
SERVER_INFO = "info"
SERVER_ERROR = "error"
SERVER_PONG = "pong"

# ---- client -> server message types ----
CLIENT_TEXT = "text"               # debug: drive the pipeline from typed text
CLIENT_AUDIO_META = "audio_meta"   # precedes a binary audio frame from the mic
CLIENT_SET_MODE = "set_mode"
CLIENT_PING = "ping"


def state_msg(state: str) -> Dict[str, Any]:
    return {"type": SERVER_STATE, "state": state}


def transcript_msg(text: str, lang: str) -> Dict[str, Any]:
    return {"type": SERVER_TRANSCRIPT, "text": text, "lang": lang}


def llm_text_msg(text: str, final: bool = False) -> Dict[str, Any]:
    return {"type": SERVER_LLM_TEXT, "text": text, "final": final}


def mode_msg(mode: str, response_lang: str) -> Dict[str, Any]:
    return {"type": SERVER_MODE, "mode": mode, "response_lang": response_lang}


def info_msg(text: str) -> Dict[str, Any]:
    return {"type": SERVER_INFO, "text": text}


def error_msg(text: str) -> Dict[str, Any]:
    return {"type": SERVER_ERROR, "text": text}
