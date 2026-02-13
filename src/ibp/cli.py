from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .approval import approve_injections
from .headings import generate_candidates, write_proposed_artifacts
from .ingest import book_catcher_scan, build_manifest, collect_html_files, resolve_book
from .plans import write_chunk_plan
from .utils import now_run_id


def _archive_book_runs(runs_root: Path, book_id: str) -> None:
    if not runs_root.exists():
        return
    for p in runs_root.iterdir():
        if p.is_dir() and (p / book_id).exists():
            archive = runs_root / "_ARCHIVE" / book_id / p.name
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(archive))


def cmd_propose(args: argparse.Namespace) -> int:
    fixtures_root = Path(args.fixtures_root)
    runs_root = Path(args.runs_root)
    run_id = args.run_id or now_run_id()

    if args.clean_book:
        _archive_book_runs(runs_root, args.book_id)

    run_dir = runs_root / run_id / args.book_id
    run_dir.mkdir(parents=True, exist_ok=True)

    book = resolve_book(fixtures_root, args.book_id)
    html_files = collect_html_files(book)

    build_manifest(book, html_files, run_dir / "manifest.json")
    scan = book_catcher_scan(html_files, run_dir / "bookcatcher.scan.json")

    must_not = Path(args.must_not_path)
    candidates = generate_candidates(html_files, must_not)
    heading_summary = write_proposed_artifacts(candidates, run_dir)
    write_chunk_plan(run_dir, args.book_id, heading_summary, scan)

    print(f"Run created: {run_dir}")
    print("Approval gate reached: review heading_injections.proposed.jsonl before any apply stage.")
"""Command line interface for the Islamic Book Processor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ibp.review.io import read_decisions, read_json, read_jsonl, write_json, write_jsonl
from ibp.review.models import DecisionAction, EXERCISE_FAMILY_KEYWORDS, ReviewSummary


DECISIONS_FILE = "review.decisions.jsonl"


def _is_exercise_family(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(item.get(key, "")) for key in ("title", "heading", "label", "route", "topic")
    )
    return any(keyword in text for keyword in EXERCISE_FAMILY_KEYWORDS)


def _item_id(item: dict[str, Any], idx: int) -> str:
    return str(item.get("id") or item.get("item_id") or f"item-{idx}")


def _summary_to_markdown(summary: ReviewSummary) -> str:
    lines = [
        "# Review Summary",
        "",
        f"- run_id: `{summary.run_id}`",
        f"- book_id: `{summary.book_id}`",
        f"- resolved: `{summary.resolved}`",
        f"- approved: `{summary.approved}`",
        f"- edited: `{summary.edited}`",
        f"- rejected: `{summary.rejected}`",
        f"- blocked: `{summary.blocked}`",
        f"- downstream_apply_permitted: `{str(summary.downstream_apply_permitted).lower()}`",
        "",
    ]
    if summary.blocked_items:
        lines.append("## Blocked items")
        lines.append("")
        lines.extend(f"- `{item}`" for item in summary.blocked_items)
        lines.append("")
    lines.append("Approved artifacts are emitted only when blocked=0 (fail-closed policy).")
    return "\n".join(lines) + "\n"


def run_approve(args: argparse.Namespace) -> int:
    run_dir = Path("runs") / args.run_id / args.book_id
    source_tag = args.source_tag
    out_tag = args.out_tag

    heading_in = run_dir / f"heading_injections.{source_tag}.jsonl"
    chunk_in = run_dir / f"chunk_plan.{source_tag}.json"
    decisions_path = run_dir / DECISIONS_FILE

    if not heading_in.exists() or not chunk_in.exists():
        raise FileNotFoundError("Missing proposed artifacts under run folder")

    heading_rows = read_jsonl(heading_in)
    chunk_payload = read_json(chunk_in)
    chunk_rows = list(chunk_payload.get("items", []))

    summary = ReviewSummary(run_id=args.run_id, book_id=args.book_id)

    if not decisions_path.exists():
        summary.blocked = len(heading_rows) + len(chunk_rows)
        summary.blocked_items = [
            f"heading_injections:{_item_id(item, idx)}" for idx, item in enumerate(heading_rows, start=1)
        ] + [f"chunk_plan:{_item_id(item, idx)}" for idx, item in enumerate(chunk_rows, start=1)]
        (run_dir / "review_summary.md").write_text(_summary_to_markdown(summary), encoding="utf-8")
        return 2

    decisions = read_decisions(decisions_path)
    decision_map = {(d.artifact, d.item_id): d for d in decisions}

    approved_headings: list[dict[str, Any]] = []
    approved_chunks: list[dict[str, Any]] = []

    def consume(artifact: str, rows: list[dict[str, Any]], sink: list[dict[str, Any]]) -> None:
        for idx, row in enumerate(rows, start=1):
            item_id = _item_id(row, idx)
            if _is_exercise_family(row):
                row["review_required"] = True
            decision = decision_map.get((artifact, item_id))
            if decision is None:
                summary.blocked += 1
                summary.blocked_items.append(f"{artifact}:{item_id}")
                continue

            summary.resolved += 1
            if decision.decision is DecisionAction.APPROVE:
                summary.approved += 1
                sink.append(row)
            elif decision.decision is DecisionAction.EDIT:
                summary.edited += 1
                if decision.edited_value is None:
                    summary.blocked += 1
                    summary.blocked_items.append(f"{artifact}:{item_id}:missing_edit_payload")
                    continue
                edited = dict(row)
                edited.update(decision.edited_value)
                sink.append(edited)
            elif decision.decision is DecisionAction.REJECT:
                summary.rejected += 1

    consume("heading_injections", heading_rows, approved_headings)
    consume("chunk_plan", chunk_rows, approved_chunks)

    summary_path = run_dir / "review_summary.md"
    summary_path.write_text(_summary_to_markdown(summary), encoding="utf-8")

    if summary.blocked > 0:
        return 3

    heading_out = run_dir / f"heading_injections.{out_tag}.jsonl"
    chunk_out = run_dir / f"chunk_plan.{out_tag}.json"
    write_jsonl(heading_out, approved_headings)
    chunk_payload["items"] = approved_chunks
    chunk_payload["review_required"] = False
    write_json(chunk_out, chunk_payload)

    return 0
import json
from datetime import datetime, timezone
from pathlib import Path

from ibp.logging import configure_run_logger
from ibp.run_context import RunContext


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_scan(args: argparse.Namespace) -> int:
    ctx = RunContext.create(book_id=args.book_id, runs_dir=args.runs_dir)
    logger = configure_run_logger(ctx.logs_dir / "scan.log")
    logger.info("Starting deterministic scan for book_id=%s", ctx.book_id)

    _write_json(
        ctx.artifacts_dir / "scan_analysis.json",
        {
            "run_id": ctx.run_id,
            "book_id": ctx.book_id,
            "command": "scan",
            "stage": "ingest_and_deterministic_analysis",
            "created_at": _utc_now_iso(),
            "status": "completed",
        },
    )

    print(f"Created run: {ctx.run_id} at {ctx.book_dir}")
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    ctx = RunContext.create(book_id=args.book_id, runs_dir=args.runs_dir)
    logger = configure_run_logger(ctx.logs_dir / "propose.log")
    logger.info("Creating heading injection and chunk plan proposal for book_id=%s", ctx.book_id)

    _write_json(
        ctx.artifacts_dir / "proposal.json",
        {
            "run_id": ctx.run_id,
            "book_id": ctx.book_id,
            "command": "propose",
            "scope": ["heading_injection", "chunk_plan"],
            "auto_apply": False,
            "created_at": _utc_now_iso(),
            "status": "proposed",
        },
    )

    print(f"Created proposal run: {ctx.run_id} at {ctx.book_dir}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs_root) / args.run_id / args.book_id
    approved_path = approve_injections(run_dir, mode="approve_all" if args.approve_all else "reject_all")
    print(f"Wrote approval decisions: {approved_path}")
    ctx = RunContext.create(book_id=args.book_id, runs_dir=args.runs_dir)
    logger = configure_run_logger(ctx.logs_dir / "approve.log")
    logger.info("Creating approval artifact for book_id=%s", ctx.book_id)

    _write_json(
        ctx.artifacts_dir / "approval.json",
        {
            "run_id": ctx.run_id,
            "book_id": ctx.book_id,
            "command": "approve",
            "approval_only": True,
            "auto_apply": False,
            "created_at": _utc_now_iso(),
            "status": "approved_artifact_created",
        },
    )

    print(f"Created approval run: {ctx.run_id} at {ctx.book_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ibp", description="Islamic Book Processor")
    sub = p.add_subparsers(dest="cmd", required=True)

    propose = sub.add_parser("propose", help="Phase 1 deterministic proposal + approval gate")
    propose.add_argument("--book-id", required=True)
    propose.add_argument("--fixtures-root", default="fixtures/shamela_exports")
    propose.add_argument("--must-not-path", default="training/gold_snippets/must_not_heading.jsonl")
    propose.add_argument("--runs-root", default="runs")
    propose.add_argument("--run-id")
    propose.add_argument("--clean-book", action="store_true")
    propose.set_defaults(func=cmd_propose)

    approve = sub.add_parser("approve", help="Record human approval/rejection decisions")
    approve.add_argument("--runs-root", default="runs")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--book-id", required=True)
    approve.add_argument("--approve-all", action="store_true")
    approve.set_defaults(func=cmd_approve)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    parser = argparse.ArgumentParser(prog="ibp", description="Islamic Book Processor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("book_id", help="Book identifier for run-scoped outputs")
        subparser.add_argument(
            "--runs-dir",
            default="runs",
            help="Base directory where immutable run artifacts are created",
        )

    scan_parser = subparsers.add_parser("scan", help="Ingest + deterministic analysis")
    add_common_options(scan_parser)
    scan_parser.set_defaults(func=cmd_scan)

    propose_parser = subparsers.add_parser("propose", help="Heading injection + chunk plan proposal only")
    add_common_options(propose_parser)
    propose_parser.set_defaults(func=cmd_propose)

    approve_parser = subparsers.add_parser("approve", help="Create approval artifact without auto-apply")
    add_common_options(approve_parser)
    approve_parser.set_defaults(func=cmd_approve)

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
    subparsers = parser.add_subparsers(dest="command", required=True)

    approve = subparsers.add_parser("approve", help="Approve or block proposed review artifacts")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--book-id", required=True)
    approve.add_argument("--from", dest="source_tag", default="proposed")
    approve.add_argument("--out", dest="out_tag", default="approved")
    approve.set_defaults(func=run_approve)

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


if __name__ == "__main__":
    raise SystemExit(main())
    sys.exit(main())
