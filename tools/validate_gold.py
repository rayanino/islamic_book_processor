#!/usr/bin/env python3
"""Validate the gold JSONL schema for heading snippets.

Strict, fail-fast. Intended for CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_REASONS = {"title", "metadata", "footnote", "pagehead", "body_line"}
ALLOWED_LEVELS = {2, 3, None}

REQUIRED_KEYS = {
    "candidate_id",
    "book_id",
    "base_title",
    "file",
    "page_idx",
    "kind",
    "signature",
    "text",
    "context_before",
    "context_after",
    "html_excerpt",
    "gold",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="Path to heading_gold_*.jsonl")
    args = ap.parse_args()

    p = Path(args.path)
    data = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    n = 0
    for i, line in enumerate(data, start=1):
        if not line.strip():
            continue
        n += 1
        try:
            obj = json.loads(line)
        except Exception as e:
            raise SystemExit(f"Invalid JSON at line {i}: {e}")

        missing = sorted(REQUIRED_KEYS - set(obj.keys()))
        if missing:
            raise SystemExit(f"Missing keys at line {i}: {missing}")

        gold = obj.get("gold") or {}
        if "is_heading" not in gold:
            raise SystemExit(f"Missing gold.is_heading at line {i}")

        is_heading = gold.get("is_heading")
        if is_heading not in (True, False):
            raise SystemExit(f"gold.is_heading must be true/false at line {i}")

        level = gold.get("level")
        if level not in ALLOWED_LEVELS:
            raise SystemExit(f"gold.level must be 2, 3 or null at line {i}")

        reason = gold.get("reason")
        if reason not in ALLOWED_REASONS:
            raise SystemExit(f"gold.reason invalid at line {i}: {reason!r}")

        conf = gold.get("confidence")
        if not isinstance(conf, (int, float)):
            raise SystemExit(f"gold.confidence must be number at line {i}")
        if conf < 0 or conf > 1:
            raise SystemExit(f"gold.confidence out of range [0,1] at line {i}: {conf}")

        # consistency
        if is_heading is False and level is not None:
            raise SystemExit(f"gold.level must be null when is_heading=false at line {i}")
        if is_heading is True and level not in (2, 3):
            raise SystemExit(f"gold.level must be 2 or 3 when is_heading=true at line {i}")

    print(f"OK: {p} ({n} records)")


if __name__ == "__main__":
    main()
