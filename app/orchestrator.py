"""Session orchestrator: ties STT -> LLM -> TTS together per WebSocket client.

Each connected browser gets one Session. Heavy models (STT, LLM client, TTS) are
shared singletons created at app startup and injected here.

Flow for one turn:
  audio/text -> (STT) -> transcript -> LLM stream -> clause aggregation ->
  TTS per clause -> WAV frames to the browser, with character-state messages
  (thinking -> speaking -> idle) interleaved.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable, List, Optional

from . import prompts
from . import ws_protocol as wp
from .config import Settings
from .pipeline.llm import ClauseAggregator, OllamaClient
from .pipeline.stt import STT
from .pipeline.tts.base import TTSBackend

logger = logging.getLogger("vet.orchestrator")

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]

# Advance to the next syllabus item once a session had at least this many turns.
ADVANCE_AFTER_TURNS = 6


class Session:
    def __init__(
        self,
        settings: Settings,
        stt: STT,
        llm: OllamaClient,
        tts: TTSBackend,
        progress=None,       # ProgressStore | None  (wired in stage 4)
        syllabus=None,       # Syllabus | None        (wired in stage 4)
    ) -> None:
        self.s = settings
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.progress = progress
        self.syllabus = syllabus
        self.mode = settings.default_mode
        self.history: List[dict] = []
        self._session_id: Optional[int] = None
        self._last_summary: Optional[str] = None
        self._focus_item = None       # SyllabusItem | None
        self._focus_index: int = 0
        self._turn_count: int = 0

    # ---- lifecycle: load prior progress at start, persist + advance at end ----
    async def on_start(self) -> None:
        if self.progress is None:
            return
        self._session_id = await asyncio.to_thread(self.progress.start_session, self.mode)
        self._last_summary = await asyncio.to_thread(self.progress.get_last_summary)
        if self.syllabus is not None and len(self.syllabus):
            self._focus_index = await asyncio.to_thread(self.progress.current_item_index)
            self._focus_item = self.syllabus.get(self._focus_index)
        logger.info(
            "session start id=%s mode=%s focus=%s",
            self._session_id, self.mode, getattr(self._focus_item, "id", None)
        )

    async def on_end(self) -> None:
        if self.progress is None or self._session_id is None:
            return
        try:
            summary = await self._make_summary()
        except Exception:
            logger.exception("summary generation failed")
            summary = ""
        try:
            await asyncio.to_thread(self.progress.end_session, self._session_id, summary)
            if self.syllabus is not None and len(self.syllabus) and self._focus_item is not None:
                await asyncio.to_thread(self.progress.mark_topic, self._focus_item.id, "in_progress")
                if self._turn_count >= ADVANCE_AFTER_TURNS:
                    await asyncio.to_thread(self.progress.mark_topic, self._focus_item.id, "done")
                    nxt = min(self._focus_index + 1, len(self.syllabus) - 1)
                    await asyncio.to_thread(self.progress.set_current_item_index, nxt)
                    logger.info("advanced syllabus to index %d", nxt)
        except Exception:
            logger.exception("on_end persistence failed")

    # ---- mode ----
    @property
    def response_lang(self) -> str:
        return prompts.response_lang(self.mode)

    def set_mode(self, mode: str) -> None:
        if prompts.is_valid_mode(mode):
            self.mode = mode
            logger.info("mode -> %s (response_lang=%s)", mode, self.response_lang)

    # ---- turns ----
    async def handle_text(self, text: str, send_json: SendJson, send_bytes: SendBytes) -> None:
        text = text.strip()
        if not text:
            return
        await send_json(wp.transcript_msg(text, self.s.default_input_lang))
        await send_json(wp.state_msg(wp.STATE_THINKING))
        await self._run_llm(text, send_json, send_bytes)

    async def handle_audio(
        self, audio: bytes, input_lang: str, send_json: SendJson, send_bytes: SendBytes
    ) -> None:
        await send_json(wp.state_msg(wp.STATE_THINKING))
        try:
            text = await asyncio.to_thread(self.stt.transcribe, audio, input_lang)
        except Exception:
            logger.exception("STT failed")
            await send_json(wp.error_msg("STT failed — see server logs."))
            await send_json(wp.state_msg(wp.STATE_IDLE))
            return
        if not text:
            await send_json(wp.info_msg("(didn't catch that — try again)"))
            await send_json(wp.state_msg(wp.STATE_IDLE))
            return
        await send_json(wp.transcript_msg(text, input_lang))
        await self._run_llm(text, send_json, send_bytes)

    # ---- core: stream LLM, speak clause by clause ----
    async def _run_llm(self, user_text: str, send_json: SendJson, send_bytes: SendBytes) -> None:
        self.history.append({"role": "user", "content": user_text})
        messages = self._build_messages()
        aggregator = ClauseAggregator()
        collected: List[str] = []
        speaking = False

        try:
            async for delta in self.llm.chat_stream(messages):
                collected.append(delta)
                await send_json(wp.llm_text_msg(delta))
                for clause in aggregator.push(delta):
                    speaking = await self._speak(clause, send_json, send_bytes, speaking)
            tail = aggregator.flush()
            if tail:
                speaking = await self._speak(tail, send_json, send_bytes, speaking)
        except Exception:
            logger.exception("LLM/TTS turn failed")
            await send_json(
                wp.error_msg(
                    "LLM call failed. Is Ollama running on the host and the model pulled? "
                    f"({self.s.ollama_host}, model={self.s.ollama_model})"
                )
            )

        await send_json(wp.llm_text_msg("", final=True))
        assistant_text = "".join(collected).strip()
        if assistant_text:
            self.history.append({"role": "assistant", "content": assistant_text})
            self._trim_history()
            await self._record_turn(user_text, assistant_text)
        await send_json(wp.state_msg(wp.STATE_IDLE))

    async def _speak(
        self, clause: str, send_json: SendJson, send_bytes: SendBytes, speaking: bool
    ) -> bool:
        clause = clause.strip()
        if not clause:
            return speaking
        lang = self._clause_lang(clause)
        try:
            wav = await asyncio.to_thread(self.tts.synthesize, clause, lang)
        except Exception:
            logger.exception("TTS failed for clause: %r", clause)
            return speaking
        if not wav:
            return speaking
        if not speaking:
            await send_json(wp.state_msg(wp.STATE_SPEAKING))
            speaking = True
        await send_bytes(wav)
        return speaking

    # ---- helpers ----
    def _build_messages(self) -> List[dict]:
        system = prompts.build_system_prompt(self.mode, self._extra_context())
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history[-self.s.history_max_messages:])
        return messages

    def _extra_context(self) -> Optional[str]:
        parts: List[str] = []
        if self._focus_item is not None:
            parts.append(f"[Learning focus] {self._focus_item.focus_line()}")
        if self._last_summary:
            parts.append(f"[Student progress so far] {self._last_summary}")
        if self._focus_item is not None:
            if self.mode == "conversation":
                parts.append(
                    "Gently steer the chat toward the focus topic and briefly correct related mistakes."
                )
            else:
                parts.append(
                    "If my question is open-ended, you may use the focus topic as your example."
                )
        return "\n".join(parts) if parts else None

    def _clause_lang(self, text: str) -> str:
        """Pick the TTS voice language by the clause's dominant script, so the
        voice always matches the actual text (Cyrillic -> ru, Latin -> en),
        independent of the mode. Falls back to the mode's language when the
        clause has no letters (punctuation/numbers only)."""
        cyr = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
        lat = sum(1 for ch in text if "a" <= ch.lower() <= "z")
        if cyr == 0 and lat == 0:
            return self.response_lang
        return "ru" if cyr > lat else "en"

    def _trim_history(self) -> None:
        if len(self.history) > self.s.history_max_messages:
            self.history = self.history[-self.s.history_max_messages:]

    async def _record_turn(self, user_text: str, assistant_text: str) -> None:
        self._turn_count += 1
        if self.progress is not None and self._session_id is not None:
            try:
                await asyncio.to_thread(
                    self.progress.record_turn, self._session_id, user_text, assistant_text
                )
            except Exception:
                logger.exception("record_turn failed")

    async def _make_summary(self) -> str:
        if self.progress is None or self._session_id is None:
            return ""
        turns = await asyncio.to_thread(self.progress.get_session_turns, self._session_id)
        if not turns:
            return ""
        convo = "\n".join(f"Student: {u}\nTrainer: {a}" for u, a in turns[-8:])
        messages = [
            {
                "role": "system",
                "content": (
                    "You analyse an English learner's practice session. Reply with ONE short "
                    "English sentence (max 25 words) naming the student's recurring mistakes and "
                    "an approximate CEFR level. No preamble, no lists."
                ),
            },
            {"role": "user", "content": convo + "\n\n/no_think"},
        ]
        try:
            note = await self.llm.complete(messages)
        except Exception:
            logger.exception("summary LLM call failed")
            return ""
        note = re.sub(r"<think>.*?</think>", "", note, flags=re.S)
        return note.strip()[:300]
