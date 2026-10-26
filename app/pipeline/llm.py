"""LLM access via Ollama (runs natively on the host, uses the GPU).

Streams the chat response token-by-token. A :class:`ClauseAggregator` cuts the
stream into clause-sized pieces so TTS can start speaking the first phrase while
the model is still generating the rest.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator, List, Optional

import httpx

from ..config import Settings

logger = logging.getLogger("vet.llm")

_SENTENCE_END = ".!?…"
_SOFT_BREAK = ",;:—–"


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_host,
            timeout=httpx.Timeout(settings.ollama_request_timeout, connect=10.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _options(self) -> dict:
        opts = {
            "temperature": self.s.ollama_temperature,
            "num_ctx": self.s.ollama_num_ctx,
        }
        if self.s.ollama_num_gpu is not None:
            opts["num_gpu"] = self.s.ollama_num_gpu
        return opts

    async def chat_stream(self, messages: List[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.s.ollama_model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.s.ollama_keep_alive,
            "options": self._options(),
        }
        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = data.get("message") or {}
                content = msg.get("content")
                if content:
                    yield content
                if data.get("done"):
                    break

    async def complete(self, messages: List[dict]) -> str:
        """Non-streaming helper (used for the end-of-session summary)."""
        parts: List[str] = []
        async for chunk in self.chat_stream(messages):
            parts.append(chunk)
        return "".join(parts).strip()

    async def health(self) -> bool:
        try:
            r = await self._client.get("/api/tags")
            return r.status_code == 200
        except Exception:
            return False


class ClauseAggregator:
    """Accumulates streamed text and emits clause-sized chunks for TTS.

    - always flushes on sentence-ending punctuation (. ! ? …)
    - flushes on a soft break (, ; : —) once the buffer is long enough
    - hard-flushes very long runs at the last space
    """

    def __init__(self, min_chars: int = 30, hard_max: int = 220) -> None:
        self.buf = ""
        self.min_chars = min_chars
        self.hard_max = hard_max

    def push(self, text: str) -> List[str]:
        self.buf += text
        out: List[str] = []
        while True:
            clause, rest = self._extract()
            if clause is None:
                break
            if clause:
                out.append(clause)
            self.buf = rest
        return out

    def _extract(self):
        buf = self.buf
        n = len(buf)
        for i, ch in enumerate(buf):
            if ch in _SENTENCE_END:
                # don't split decimals like "3.5"
                if ch == "." and i + 1 < n and buf[i + 1].isdigit() and i > 0 and buf[i - 1].isdigit():
                    continue
                j = i + 1
                return buf[:j].strip(), buf[j:].lstrip()
            if ch in _SOFT_BREAK and (i + 1) >= self.min_chars:
                j = i + 1
                return buf[:j].strip(), buf[j:].lstrip()
        if n >= self.hard_max:
            sp = buf.rfind(" ", 0, self.hard_max)
            if sp > self.min_chars:
                return buf[:sp].strip(), buf[sp:].lstrip()
        return None, buf

    def flush(self) -> Optional[str]:
        s = self.buf.strip()
        self.buf = ""
        return s or None
