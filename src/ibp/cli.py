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
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs_root) / args.run_id / args.book_id
    approved_path = approve_injections(run_dir, mode="approve_all" if args.approve_all else "reject_all")
    print(f"Wrote approval decisions: {approved_path}")
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
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
