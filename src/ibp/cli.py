"""Command line interface for the Islamic Book Processor."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ibp.bookcatcher.scan import scan_book_html, scan_signals_jsonable
from ibp.chunking.plan import build_strict_anchor_boundaries, chunk_plan_json, chunk_plan_markdown
from ibp.headings.candidates import candidates_jsonable, extract_layer_a_candidates
from ibp.headings.scoring import score_candidates, scored_jsonable
from ibp.ingest.manifest import build_book_manifest, manifest_as_jsonable, sorted_source_files
from ibp.logging import configure_run_logger
from ibp.run_context import RunContext


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_scan(args: argparse.Namespace) -> int:
    ctx = RunContext.create(book_id=args.book_id, runs_dir=args.runs_dir)
    logger = configure_run_logger(ctx.logs_dir / "scan.log")
    logger.info("Starting deterministic scan for book_id=%s", ctx.book_id)
    _write_json(
        ctx.artifacts_dir / "scan_analysis.json",
        {
            "run_id": ctx.run_id,
            "book_id": ctx.book_id,
            "status": "completed",
            "stage": "scan",
        },
    )
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    fixtures_root = Path(args.fixtures_root)
    runs_root = Path(args.runs_root)
    run_id = args.run_id or _run_id()
    book_id = args.book_id

    source_raw = fixtures_root / book_id / "source_raw"
    if not source_raw.exists():
        raise FileNotFoundError(f"Missing source_raw: {source_raw}")

    run_dir = runs_root / run_id / book_id
    run_dir.mkdir(parents=True, exist_ok=True)

    files = sorted_source_files(source_raw)
    manifest = build_book_manifest(source_raw)
    _write_json(
        run_dir / "manifest.json",
        {
            "book_id": book_id,
            "source_raw": str(source_raw),
            "file_count": len(manifest),
            "files": manifest_as_jsonable(manifest),
        },
    )

    signals = scan_book_html(files)
    _write_json(run_dir / "bookcatcher.scan.json", scan_signals_jsonable(signals))

    candidates = []
    for path in files:
        candidates.extend(extract_layer_a_candidates(path))
    scored = score_candidates(candidates, signals)
    score_map = {row.candidate_id: row for row in scored}

    heading_rows: list[dict] = []
    proposed_lines: list[str] = []
    for cand in candidates:
        score = score_map[cand.candidate_id]
        is_heading = score.suggested_is_heading
        proposed_level = max(2, min(6, score.suggested_level))
        proposed_heading = f"{'#' * proposed_level} {cand.text}"
        if is_heading:
            proposed_lines.append(proposed_heading)
        heading_rows.append(
            {
                **asdict(cand),
                "score": score.score,
                "suggested": asdict(score),
                "proposal": "inject_heading" if is_heading else "skip",
                "review_required": True,
                "strict_anchor_eligible": is_heading,
                "is_heading": is_heading,
            }
        )

    _write_jsonl(run_dir / "heading_injections.proposed.jsonl", heading_rows)
    _write_json(run_dir / "heading_candidates.debug.json", {"items": candidates_jsonable(candidates)})
    _write_json(run_dir / "heading_scores.debug.json", {"items": scored_jsonable(scored)})

    plan = build_strict_anchor_boundaries(book_id=book_id, proposed_heading_lines=proposed_lines)
    (run_dir / "chunk_plan.proposed.json").write_text(chunk_plan_json(plan) + "\n", encoding="utf-8")
    (run_dir / "chunk_plan.proposed.md").write_text(chunk_plan_markdown(plan), encoding="utf-8")

    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs_root) / args.run_id / args.book_id
    proposed = run_dir / "heading_injections.proposed.jsonl"
    if not proposed.exists():
        raise FileNotFoundError(f"Missing proposed heading file: {proposed}")

    approved_rows: list[dict] = []
    for line in proposed.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        approve_all = bool(args.approve_all)
        row["decision"] = "approved" if approve_all and row.get("proposal") == "inject_heading" else "rejected"
        row["approved"] = row["decision"] == "approved"
        row["decided_by"] = "human_cli"
        approved_rows.append(row)

    _write_jsonl(run_dir / "heading_injections.approved.jsonl", approved_rows)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ibp", description="Islamic Book Processor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Ingest + deterministic analysis")
    scan.add_argument("book_id")
    scan.add_argument("--runs-dir", default="runs")
    scan.set_defaults(func=cmd_scan)

    propose = subparsers.add_parser("propose", help="Generate proposed heading injections and chunk plan")
    propose.add_argument("--book-id", required=True)
    propose.add_argument("--fixtures-root", default="fixtures/shamela_exports")
    propose.add_argument("--runs-root", default="runs")
    propose.add_argument("--run-id")
    propose.set_defaults(func=cmd_propose)

    approve = subparsers.add_parser("approve", help="Write heading approval decisions")
    approve.add_argument("--runs-root", default="runs")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--book-id", required=True)
    approve.add_argument("--approve-all", action="store_true")
    approve.set_defaults(func=cmd_approve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
