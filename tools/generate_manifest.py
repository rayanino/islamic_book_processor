#!/usr/bin/env python3
"""Generate a deterministic manifest of fixture/training files.

Why: downstream debugging is impossible if sample inputs change silently.
This manifest (sha256 + size + relative path) is the 'factual ground truth'
for Devin/Codex when calibrating parsers and heuristics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path('fixtures'), help='Root folder to scan')
    ap.add_argument('--extra', type=Path, action='append', default=[], help='Additional roots to scan (repeatable)')
    ap.add_argument('--out', type=Path, default=Path('fixtures/manifests/manifest.json'))
    args = ap.parse_args()

    roots = [args.root] + list(args.extra)

    files: list[Path] = []
    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob('*'):
            if p.is_file():
                files.append(p)

    files.sort(key=lambda p: str(p).lower())

    entries = []
    for p in files:
        entries.append({
            'path': (p.relative_to(args.root).as_posix() if p.is_relative_to(args.root) else p.as_posix()),
            'size': p.stat().st_size,
            'sha256': sha256_file(p),
        })

    out = {
        'roots': [r.as_posix() for r in roots],
        'file_count': len(entries),
        'entries': entries,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Wrote: {args.out} ({len(entries)} files)")


if __name__ == '__main__':
    main()
