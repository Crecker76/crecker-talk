"""FastAPI entrypoint: serves the frontend and runs the voice pipeline.

Heavy components (STT model, Ollama client, TTS backend) are created once at
startup and shared across WebSocket sessions. Each browser connection gets its
own :class:`app.orchestrator.Session` (conversation history, mode).
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import prompts
from . import ws_protocol as wp
from .config import get_settings
from .orchestrator import Session
from .pipeline.llm import OllamaClient
from .pipeline.stt import STT
from .pipeline.tts import get_tts_backend

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("vet")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up: building pipeline components")
    app.state.stt = STT(settings)
    app.state.llm = OllamaClient(settings)
    app.state.tts = get_tts_backend(settings)

    # Warm up STT + TTS in the background so the first utterance isn't slow.
    # Failures here are non-fatal (e.g. offline on first run); they surface per turn.
    async def _warmup():
        try:
            await asyncio.to_thread(app.state.stt.warmup)
            logger.info("STT warmed up")
        except Exception:
            logger.exception("STT warmup failed (will retry on first use)")
        try:
            await asyncio.to_thread(app.state.tts.warmup, prompts.response_lang(settings.default_mode))
            logger.info("TTS warmed up")
        except Exception:
            logger.exception("TTS warmup failed (will retry on first use)")

    warmup_task = asyncio.create_task(_warmup())
    try:
        yield
    finally:
        warmup_task.cancel()
        await app.state.llm.aclose()
        logger.info("Shutdown complete")


app = FastAPI(title="Voice English Trainer", version=__version__, lifespan=lifespan)


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


@app.get("/api/ollama")
async def api_ollama() -> dict:
    reachable = await app.state.llm.health()
    return {"reachable": reachable, "host": settings.ollama_host, "model": settings.ollama_model}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WS client connected")

    session = Session(
        settings,
        stt=websocket.app.state.stt,
        llm=websocket.app.state.llm,
        tts=websocket.app.state.tts,
    )
    await session.on_start()

    async def _send_json(obj: dict) -> None:
        await send_json(websocket, obj)

    async def _send_bytes(data: bytes) -> None:
        await websocket.send_bytes(data)

    await _send_json(wp.state_msg(wp.STATE_IDLE))
    await _send_json(wp.mode_msg(session.mode, session.response_lang))

    pending_audio_lang = settings.default_input_lang

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
                    await _send_json(wp.error_msg("bad json"))
                    continue
                mtype = data.get("type")

                if mtype == wp.CLIENT_PING:
                    await _send_json({"type": wp.SERVER_PONG})

                elif mtype == wp.CLIENT_SET_MODE:
                    session.set_mode(data.get("mode", session.mode))
                    await _send_json(wp.mode_msg(session.mode, session.response_lang))

                elif mtype == wp.CLIENT_AUDIO_META:
                    pending_audio_lang = data.get("input_lang", settings.default_input_lang)
                    if data.get("mode"):
                        session.set_mode(data["mode"])

                elif mtype == wp.CLIENT_TEXT:
                    if data.get("mode"):
                        session.set_mode(data["mode"])
                    await session.handle_text(data.get("text", ""), _send_json, _send_bytes)

            elif data_bytes is not None:
                await session.handle_audio(data_bytes, pending_audio_lang, _send_json, _send_bytes)

    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception:
        logger.exception("WS handler error")
    finally:
        await session.on_end()


# Mount the static frontend LAST so /ws, /healthz and /api/* take precedence.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
