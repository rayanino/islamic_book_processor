from __future__ import annotations

import json
from pathlib import Path

from .utils import write_jsonl


def approve_injections(run_dir: Path, mode: str = "approve_all") -> Path:
    proposed = run_dir / "heading_injections.proposed.jsonl"
    if not proposed.exists():
        raise FileNotFoundError(f"Missing proposed file: {proposed}")

    out = run_dir / "heading_injections.approved.jsonl"
    rows = []
    with proposed.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if mode == "approve_all" and row.get("proposal") == "inject_heading":
                row["decision"] = "approved"
            else:
                row["decision"] = "rejected"
            row["decided_by"] = "human_cli"
            rows.append(row)
    write_jsonl(out, rows)
    return out
