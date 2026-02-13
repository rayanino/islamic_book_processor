#!/usr/bin/env python3
"""Deterministically split a gold JSONL into train/holdout.

Split rule: holdout if sha256(candidate_id) % denom == 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

def is_holdout(candidate_id: str, denom: int) -> bool:
    h = int(hashlib.sha256(candidate_id.encode('utf-8')).hexdigest()[:8], 16)
    return (h % denom) == 0

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True, help='input JSONL')
    ap.add_argument('--out-train', required=True)
    ap.add_argument('--out-holdout', required=True)
    ap.add_argument('--denom', type=int, default=5, help='1/denom goes to holdout (default 5 => 20%)')
    args = ap.parse_args()

    inp = Path(args.inp)
    train_path = Path(args.out_train)
    holdout_path = Path(args.out_holdout)

    train_lines=[]
    holdout_lines=[]

    for line in inp.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        cid = obj.get('candidate_id') or ''
        if not cid:
            continue
        if is_holdout(cid, args.denom):
            holdout_lines.append(json.dumps(obj, ensure_ascii=False))
        else:
            train_lines.append(json.dumps(obj, ensure_ascii=False))

    train_path.parent.mkdir(parents=True, exist_ok=True)
    holdout_path.parent.mkdir(parents=True, exist_ok=True)
    train_path.write_text('\n'.join(train_lines) + '\n', encoding='utf-8')
    holdout_path.write_text('\n'.join(holdout_lines) + '\n', encoding='utf-8')
    print(f'train={len(train_lines)} holdout={len(holdout_lines)}')

if __name__ == '__main__':
    main()
