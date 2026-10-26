"""Learning program loaded from syllabus.yaml.

Flattened into an ordered list of items; the orchestrator injects the current
focus item into the LLM context and advances through the list as the student
practises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger("vet.syllabus")


@dataclass
class SyllabusItem:
    id: str
    level: str
    topic: str
    rule: str
    examples: List[str] = field(default_factory=list)

    def focus_line(self) -> str:
        ex = f" e.g. {self.examples[0]}" if self.examples else ""
        return f"{self.level} — {self.topic}: {self.rule}{ex}"


class Syllabus:
    def __init__(self, items: List[SyllabusItem]) -> None:
        self.items = items

    def __len__(self) -> int:
        return len(self.items)

    def get(self, index: int) -> Optional[SyllabusItem]:
        if not self.items:
            return None
        index = max(0, min(index, len(self.items) - 1))
        return self.items[index]

    @classmethod
    def load(cls, path: str) -> "Syllabus":
        p = Path(path)
        if not p.exists():
            logger.warning("syllabus not found at %s — running without a program", path)
            return cls([])
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.exception("failed to parse syllabus %s", path)
            return cls([])

        items: List[SyllabusItem] = []
        for level_block in data.get("levels", []) or []:
            level = str(level_block.get("level", "")).strip()
            for topic in level_block.get("topics", []) or []:
                items.append(
                    SyllabusItem(
                        id=str(topic.get("id") or f"{level}-{len(items)}"),
                        level=level,
                        topic=str(topic.get("topic", "")).strip(),
                        rule=str(topic.get("rule", "")).strip(),
                        examples=[str(e) for e in (topic.get("examples") or [])],
                    )
                )
        logger.info("Loaded syllabus: %d items", len(items))
        return cls(items)
