"""Learning progress persisted in SQLite (a mounted volume: data/progress.db).

Tracks sessions, per-turn utterances, a rolling progress summary, and the
current position in the syllabus. A short summary of the previous session is
injected into the LLM context at the start of the next one; it is refreshed at
session end. All methods are synchronous — call them via asyncio.to_thread().
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("vet.progress")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    ended_at   TEXT,
    mode       TEXT,
    turns      INTEGER DEFAULT 0,
    summary    TEXT
);
CREATE TABLE IF NOT EXISTS turns (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER,
    created_at     TEXT,
    user_text      TEXT,
    assistant_text TEXT
);
CREATE TABLE IF NOT EXISTS topics (
    topic_id   TEXT PRIMARY KEY,
    status     TEXT,           -- pending | in_progress | done
    updated_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProgressStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        logger.info("Progress DB ready at %s", db_path)

    # ---- meta KV ----
    def _get_meta(self, key: str) -> Optional[str]:
        cur = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ---- sessions ----
    def start_session(self, mode: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions(started_at, mode, turns) VALUES(?, ?, 0)",
                (_now(), mode),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def record_turn(self, session_id: int, user_text: str, assistant_text: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns(session_id, created_at, user_text, assistant_text) "
                "VALUES(?, ?, ?, ?)",
                (session_id, _now(), user_text, assistant_text),
            )
            self._conn.execute(
                "UPDATE sessions SET turns = turns + 1 WHERE id = ?", (session_id,)
            )
            self._conn.commit()

    def end_session(self, session_id: int, summary: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ?, summary = ? WHERE id = ?",
                (_now(), summary, session_id),
            )
            if summary:
                self._set_meta("last_summary", summary)
            self._conn.commit()

    def session_turn_count(self, session_id: int) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT turns FROM sessions WHERE id = ?", (session_id,))
            row = cur.fetchone()
            return int(row["turns"]) if row else 0

    def get_session_turns(self, session_id: int) -> List[Tuple[str, str]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT user_text, assistant_text FROM turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            return [(r["user_text"], r["assistant_text"]) for r in cur.fetchall()]

    # ---- rolling summary ----
    def get_last_summary(self) -> Optional[str]:
        with self._lock:
            return self._get_meta("last_summary")

    # ---- syllabus position ----
    def current_item_index(self) -> int:
        with self._lock:
            raw = self._get_meta("current_item_index")
        try:
            return int(raw) if raw is not None else 0
        except ValueError:
            return 0

    def set_current_item_index(self, index: int) -> None:
        with self._lock:
            self._set_meta("current_item_index", str(max(0, index)))
            self._conn.commit()

    def mark_topic(self, topic_id: str, status: str) -> None:
        if not topic_id:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO topics(topic_id, status, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(topic_id) DO UPDATE SET status = excluded.status, "
                "updated_at = excluded.updated_at",
                (topic_id, status, _now()),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
