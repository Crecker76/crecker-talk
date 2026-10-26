"""FastAPI entrypoint: serves the frontend and the WebSocket pipeline.

Stage 1 is a text echo loop that exercises the full skeleton (static files +
WebSocket + character states) without any audio. Later stages replace the echo
in ``handle_text_message`` / the binary branch with the real VAD->STT->LLM->TTS
pipeline (see app.orchestrator).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import ws_protocol as wp
from .config import get_settings

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("vet")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Voice English Trainer", version=__version__)


async def send_json(websocket: WebSocket, obj: dict) -> None:
    await websocket.send_text(json.dumps(obj, ensure_ascii=False))


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/config")
async def api_config() -> dict:
    return {
        "default_mode": settings.default_mode,
        "default_input_lang": settings.default_input_lang,
        "modes": ["conversation", "explain"],
        "input_langs": ["en", "ru"],
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WS client connected")
    await send_json(websocket, wp.state_msg(wp.STATE_IDLE))
    await send_json(
        websocket, wp.mode_msg(settings.default_mode, _response_lang(settings.default_mode))
    )
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            text = message.get("text")
            data_bytes = message.get("bytes")
            if text is not None:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    await send_json(websocket, wp.error_msg("bad json"))
                    continue
                await handle_text_message(websocket, data)
            elif data_bytes is not None:
                # Stage 1: audio pipeline not wired yet.
                await send_json(
                    websocket, wp.info_msg("Audio not available in stage 1 (text echo only).")
                )
    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception:  # noqa: BLE001 - keep the socket alive against single-turn errors
        logger.exception("WS handler error")


async def handle_text_message(websocket: WebSocket, data: dict) -> None:
    mtype = data.get("type")

    if mtype == wp.CLIENT_PING:
        await send_json(websocket, {"type": wp.SERVER_PONG})
        return

    if mtype == wp.CLIENT_SET_MODE:
        mode = data.get("mode", settings.default_mode)
        await send_json(websocket, wp.mode_msg(mode, _response_lang(mode)))
        await send_json(websocket, wp.info_msg(f"mode -> {mode}"))
        return

    if mtype == wp.CLIENT_TEXT:
        user_text = (data.get("text") or "").strip()
        if not user_text:
            return
        await _echo_reply(websocket, user_text)
        return


async def _echo_reply(websocket: WebSocket, user_text: str) -> None:
    """Stage-1 stand-in for the LLM: streams a canned reply word by word so the
    character state machine (thinking -> speaking -> idle) is visible."""
    await send_json(websocket, wp.transcript_msg(user_text, settings.default_input_lang))
    await send_json(websocket, wp.state_msg(wp.STATE_THINKING))
    await asyncio.sleep(0.4)
    reply = f"Echo: {user_text}"
    await send_json(websocket, wp.state_msg(wp.STATE_SPEAKING))
    for word in reply.split(" "):
        await send_json(websocket, wp.llm_text_msg(word + " "))
        await asyncio.sleep(0.06)
    await send_json(websocket, wp.llm_text_msg("", final=True))
    await send_json(websocket, wp.state_msg(wp.STATE_IDLE))


def _response_lang(mode: str) -> str:
    return "ru" if mode == "explain" else "en"


# Mount the static frontend LAST so /ws, /healthz and /api/* take precedence.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
