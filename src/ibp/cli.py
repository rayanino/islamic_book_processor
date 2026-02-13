from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ibp.bookcatcher.scan import scan_book_html
from ibp.chunking.plan import build_strict_anchor_boundaries, chunk_plan_json, chunk_plan_markdown
from ibp.headings.candidates import extract_layer_a_candidates
from ibp.headings.scoring import score_candidates
from ibp.ingest.manifest import sorted_source_files

EXIT_APPROVAL_REQUIRED = 30


def _run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def _collect_books(fixtures_root: Path, book_id: str | None) -> list[Path]:
    books = [p for p in sorted(fixtures_root.iterdir()) if p.is_dir()]
    if book_id:
        books = [p for p in books if p.name == book_id]
    return books


def cmd_propose(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    fixtures_root = repo_root / "fixtures" / "shamela_exports"
    run_id = args.run_id or _run_id()

    books = _collect_books(fixtures_root, args.book_id)
    if not books:
        raise SystemExit("No books found for propose.")

    for book_dir in books:
        book_id = book_dir.name
        source_raw = book_dir / "source_raw"
        files = sorted_source_files(source_raw)
        signals = scan_book_html(files)

        candidates = []
        for f in files:
            candidates.extend(extract_layer_a_candidates(f))
        scored = score_candidates(candidates, signals)
        scores_by_id = {s.candidate_id: s for s in scored}

        injections = []
        anchor_lines = []
        for cand in candidates:
            s = scores_by_id[cand.candidate_id]
            if not s.suggested_is_heading:
                continue
            heading_line = f"{'#' * s.suggested_level} {cand.text}"
            if s.suggested_level < 2 or s.suggested_level > 6:
                continue
            injections.append(
                {
                    "candidate_id": cand.candidate_id,
                    "book_id": book_id,
                    "file": cand.file,
                    "line_no": cand.line_no,
                    "proposed_heading": heading_line,
                    "strict_anchor_eligible": heading_line.startswith(("## ", "### ", "#### ", "##### ", "###### ")),
                    "review_required": True,
                    "status": "proposed",
                    "rationale": s.rationale,
                    "score": s.score,
                }
            )
            anchor_lines.append(heading_line)

        plan = build_strict_anchor_boundaries(book_id=book_id, proposed_heading_lines=anchor_lines)

        out_dir = repo_root / "runs" / run_id / book_id / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)

        with (out_dir / "heading_injections.proposed.jsonl").open("w", encoding="utf-8") as f:
            for row in injections:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        (out_dir / "chunk_plan.proposed.json").write_text(chunk_plan_json(plan), encoding="utf-8")
        (out_dir / "chunk_plan.proposed.md").write_text(chunk_plan_markdown(plan), encoding="utf-8")


    print(f"run_id={run_id}")
    print("approval required: propose stage completed; apply stage not executed")
    return EXIT_APPROVAL_REQUIRED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ibp")
    sub = parser.add_subparsers(dest="command", required=True)

    propose = sub.add_parser("propose", help="Generate deterministic proposed artifacts only")
    propose.add_argument("--repo-root", default=".")
    propose.add_argument("--run-id")
    propose.add_argument("--book-id")
    propose.set_defaults(func=cmd_propose)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
