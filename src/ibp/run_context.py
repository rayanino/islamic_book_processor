"""Run context helpers for immutable run artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ibp.config import resolve_runs_dir, sanitize_path_component


@dataclass(frozen=True)
class RunContext:
    run_id: str
    book_id: str
    root_dir: Path
    book_dir: Path
    logs_dir: Path
    artifacts_dir: Path

    @classmethod
    def create(cls, book_id: str, runs_dir: str | Path = "runs") -> "RunContext":
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_book_id = sanitize_path_component(book_id)
        root_dir = resolve_runs_dir(runs_dir) / run_id
        book_dir = root_dir / safe_book_id
        logs_dir = book_dir / "logs"
        artifacts_dir = book_dir / "artifacts"

        logs_dir.mkdir(parents=True, exist_ok=False)
        artifacts_dir.mkdir(parents=True, exist_ok=False)

        return cls(
            run_id=run_id,
            book_id=safe_book_id,
            root_dir=root_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            artifacts_dir=artifacts_dir,
        )
