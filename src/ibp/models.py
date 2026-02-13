from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BookInput:
    book_id: str
    book_dir: Path


@dataclass(frozen=True)
class HeadingCandidate:
    source_file: str
    page_index: int
    line_index: int
    text: str
    normalized_text: str
    score: float
    reasons: list[str]
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
