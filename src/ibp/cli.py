"""Command line interface for the Islamic Book Processor."""

from __future__ import annotations

import argparse
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
