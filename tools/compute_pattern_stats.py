#!/usr/bin/env python3
"""Compute simple HTML signature counts for Shamela-exported fixtures.

Intentionally dumb, deterministic, and offline.
Helps calibrate heading-detection heuristics (Layer A/B) without any LLM.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

DEFAULT_PATTERNS = {
    # Shamela wrappers / page markers
    "PageText": re.compile(r"PageText"),
    "PageHead": re.compile(r"PageHead"),
    "PageNumber": re.compile(r"PageNumber"),
    "PartName": re.compile(r"PartName"),

    # Common heading-like structures
    "span.title": re.compile(r"span\s+class=\"title\"|span\s+class='title'|data-type=\"title\""),
    "align.center": re.compile(r"align\s*=\s*\"center\"|align\s*=\s*'center'"),
    "style.text-align.center": re.compile(r"text-align\s*:\s*center"),
    "<center>": re.compile(r"<\s*center\b"),
    "<b>/<strong>": re.compile(r"<\s*(b|strong)\b"),
    "<font>": re.compile(r"<\s*font\b"),
    "footnote": re.compile(r"class=\"footnote\"|class='footnote'|footnote"),
    "<hr>": re.compile(r"<\s*hr\b"),
}

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="fixtures/shamela_exports", help="root folder containing BK*/ subfolders")
    ap.add_argument("--out", default="fixtures/manifests/pattern_stats.json", help="output json path")
    args = ap.parse_args()

    root = Path(args.root)
    out = Path(args.out)

    result: dict = {"books": {}, "totals": {}}
    totals = Counter()

    for book_dir in sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith("BK")]):
        meta_path = book_dir / "meta.json"
        title_ar = None
        if meta_path.exists():
            try:
                meta = read_json(meta_path)
                title_ar = meta.get("title_ar") or meta.get("title") or meta.get("base_title")
            except Exception:
                title_ar = None

        book_counts = Counter()
        file_count = 0
        bytes_total = 0

        # Count patterns across all .htm/.html in source_raw
        src = book_dir / "source_raw"
        if not src.exists():
            continue

        for f in sorted(src.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() not in {".htm", ".html"}:
                continue
            file_count += 1
            try:
                data = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            bytes_total += f.stat().st_size

            for name, rx in DEFAULT_PATTERNS.items():
                n = len(rx.findall(data))
                if n:
                    book_counts[name] += n
                    totals[name] += n

        result["books"][book_dir.name] = {
            "title_ar": title_ar,
            "html_files": file_count,
            "bytes_total": bytes_total,
            "counts": dict(book_counts),
        }

    result["totals"] = dict(totals)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote: {out.resolve()}")  # deterministic destination

if __name__ == "__main__":
    main()
