# Gold snippet labeling

Files:

- `heading_candidates_v3.jsonl`: candidates produced by a prior extractor (each record contains `html_excerpt` + local context).
- `heading_gold_v3.jsonl`: your manual labels (198 records).
- `heading_gold_v3.cleaned.jsonl`: same labels, but:
  - UTF‑8 no BOM
  - `gold.reason` normalized (`metadata` for `kind=metadata` false examples)
- `splits/train.jsonl` and `splits/holdout.jsonl`: deterministic 80/20 split derived from `heading_gold_v3.cleaned.jsonl`.
- `must_not_heading.jsonl`: 40 tricky false positives (style looks like a heading but must never be injected).

Schema (per record):

- `gold.is_heading` (bool)
- `gold.level` (2 or 3 when heading; else null)
- `gold.reason` (title / metadata / footnote / pagehead / body_line)
- `gold.confidence` (0..1)

Validation:

```bash
python tools/validate_gold.py --path training/gold_snippets/heading_gold_v3.cleaned.jsonl
```

