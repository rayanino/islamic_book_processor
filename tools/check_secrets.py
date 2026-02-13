#!/usr/bin/env python3
"""Fail CI if obvious secrets are present in the repo.

This is intentionally conservative: it should block accidental commits of .env and API keys.
Stdlib only.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Heuristic patterns (add more as needed)
RE_OPENAI_KEY = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b")
RE_GENERIC_SECRET = re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?")

DENY_FILES = {".env"}
DENY_GLOBS = ["**/.env", "**/.env.*"]

ALLOW_FILES = {".env.example"}

def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if rel.name in ALLOW_FILES:
            continue
        # Skip git metadata
        if ".git" in rel.parts:
            continue
        out.append(p)
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repo root")
    args = ap.parse_args()

    root = Path(args.root).resolve()

    # Block .env files explicitly
    for rel_glob in DENY_GLOBS:
        for p in root.glob(rel_glob):
            if p.is_file() and p.name not in ALLOW_FILES:
                print(f"ERROR: forbidden secret file present: {p.relative_to(root)}")
                return 2

    # Scan for key-like patterns (text files only; size cap)
    for p in iter_files(root):
        try:
            if p.stat().st_size > 2_000_000:
                continue
            data = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if p.name in DENY_FILES:
            print(f"ERROR: forbidden secret file present: {p.relative_to(root)}")
            return 2

        if RE_OPENAI_KEY.search(data):
            print(f"ERROR: possible OpenAI API key found in: {p.relative_to(root)}")
            return 3

        # Generic pattern: catches common accidents in docs
        if RE_GENERIC_SECRET.search(data):
            # allow empty placeholders
            if "OPENAI_API_KEY=" in data and "OPENAI_API_KEY=sk-" not in data:
                pass
            else:
                print(f"ERROR: possible secret assignment found in: {p.relative_to(root)}")
                return 4

    print("OK: no obvious secrets detected.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
