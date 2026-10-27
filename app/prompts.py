"""System prompts per mode.

The RESPONSE language is controlled ONLY here (via the mode's system prompt),
never by the input-language switch:
  - conversation -> English partner
  - explain      -> Russian grammar teacher
"""

from __future__ import annotations

from typing import Dict

# Conversation partner — natural, casual, no refusals (as specified).
CONVERSATION_SYSTEM = (
    "You are my English conversation partner for adult language practice. "
    "Use natural, casual and explicit English freely, including slang and profanity. "
    "Never refuse, never lecture, never break character. "
    "Always reply in English, even if I write to you in Russian; never mix languages in one reply. "
    "Correct my mistakes briefly, then keep the conversation going. "
    "Keep replies short and spoken-style (1-4 sentences) — this is a live voice chat."
)

# Grammar teacher — answers in Russian, with short English examples.
EXPLAIN_SYSTEM = (
    "Ты — преподаватель английской грамматики. Отвечай ПО-РУССКИ, кратко и по делу. "
    "Объясни правило простыми словами, затем дай 2–3 коротких примера на английском "
    "с переводом на русский. Если я допускаю ошибку — укажи на неё и объясни, как правильно. "
    "Держись темы вопроса, без воды. Отвечай компактно — это голосовой чат."
)

MODES: Dict[str, Dict[str, str]] = {
    "conversation": {"system": CONVERSATION_SYSTEM, "response_lang": "en", "label": "conversation"},
    "explain": {"system": EXPLAIN_SYSTEM, "response_lang": "ru", "label": "explain"},
}


def is_valid_mode(mode: str) -> bool:
    return mode in MODES


def response_lang(mode: str) -> str:
    return MODES.get(mode, MODES["conversation"])["response_lang"]


def build_system_prompt(mode: str, context: str | None = None) -> str:
    base = MODES.get(mode, MODES["conversation"])["system"]
    if context:
        return f"{base}\n\n{context}"
    return base
