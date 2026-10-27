"""System prompts per mode.

Mode selects the ROLE only. The REPLY LANGUAGE mirrors the language the user used
in their message (detected per turn in the orchestrator): write Russian -> get
Russian, write English -> get English. The TTS voice then follows the reply text.
"""

from __future__ import annotations

from typing import Dict, Optional

LANG_NAMES = {"en": "English", "ru": "Russian"}

# Casual conversation partner.
CONVERSATION_SYSTEM = (
    "You are my conversation partner for adult language practice. "
    "Be natural, casual and explicit; slang and profanity are fine. "
    "Never refuse, never lecture, never break character. "
    "Correct my mistakes briefly, then keep the conversation going. "
    "Keep replies short and spoken-style (1-4 sentences) — this is a live voice chat."
)

# Grammar teacher.
EXPLAIN_SYSTEM = (
    "You are a patient English-grammar teacher. Explain the rule I ask about in simple "
    "terms with 2-3 short examples; keep the example sentences in English and add a "
    "translation when you are replying in another language. If I make a mistake, point it "
    "out and show the correct form. Stay on topic and keep it compact — this is a voice chat."
)

MODES: Dict[str, Dict[str, str]] = {
    "conversation": {"system": CONVERSATION_SYSTEM, "response_lang": "en", "label": "conversation"},
    "explain": {"system": EXPLAIN_SYSTEM, "response_lang": "ru", "label": "explain"},
}


def is_valid_mode(mode: str) -> bool:
    return mode in MODES


def response_lang(mode: str) -> str:
    # Nominal default for a mode (e.g. to warm up a TTS voice). The ACTUAL reply
    # language is decided per turn by mirroring the user's input language.
    return MODES.get(mode, MODES["conversation"])["response_lang"]


def build_system_prompt(mode: str, reply_lang: str = "en", context: Optional[str] = None) -> str:
    base = MODES.get(mode, MODES["conversation"])["system"]
    lang = LANG_NAMES.get(reply_lang, "English")
    directive = (
        "IMPORTANT: Reply in the SAME language I write/speak in. "
        f"For this message, write your ENTIRE reply in {lang}. Never mix languages."
    )
    parts = [base, directive]
    if context:
        parts.append(context)
    return "\n\n".join(parts)
