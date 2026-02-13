"""Command line interface for the Islamic Book Processor (Phase 1 deterministic)."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ibp.bookcatcher.scan import scan_book_html, scan_signals_jsonable
from ibp.chunking.plan import build_strict_anchor_boundaries, chunk_plan_markdown
from ibp.headings.candidates import extract_layer_a_candidates
from ibp.headings.scoring import score_candidates
from ibp.ingest.manifest import build_book_manifest, manifest_as_jsonable, sorted_source_files
from ibp.qa.report import write_run_report
from ibp.review.io import read_jsonl, write_json, write_jsonl
from ibp.review.models import DecisionAction, DecisionRecord, EXERCISE_FAMILY_KEYWORDS, ReviewSummary

STRICT_ANCHOR_REGEX = r"^#{2,6}\s+"


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_run_dirs(runs_root: Path, run_id: str, book_id: str) -> tuple[Path, Path, Path]:
    run_book_dir = runs_root / run_id / book_id
    artifacts_dir = run_book_dir / "artifacts"
    logs_dir = run_book_dir / "logs"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return run_book_dir, artifacts_dir, logs_dir


def _archive_book_outputs(runs_root: Path, book_id: str) -> int:
    if not runs_root.exists():
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    moved = 0
    for candidate in sorted(runs_root.iterdir()):
        if not candidate.is_dir() or candidate.name == "_ARCHIVE":
            continue
        book_dir = candidate / book_id
        if not book_dir.exists():
            continue
        dest = runs_root / "_ARCHIVE" / book_id / stamp / candidate.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(book_dir), str(dest))
        moved += 1
    return moved


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("\u200c", " ").split())


def _load_must_not(path: Path) -> set[str]:
    if not path.exists():
        return set()
    blocked: set[str] = set()
    for row in read_jsonl(path):
        text = str(row.get("text") or row.get("snippet") or "").strip()
        if text:
            blocked.add(_normalize_text(text))
    return blocked


def _item_id(item: dict[str, Any], index: int, prefix: str) -> str:
    raw = item.get("candidate_id") or item.get("anchor") or item.get("item_id")
    if raw:
        return str(raw)
    return f"{prefix}-{index}"


def _is_exercise_text(text: str) -> bool:
    return any(token in text for token in EXERCISE_FAMILY_KEYWORDS)


def _write_run_state(run_book_dir: Path, state: str, details: dict[str, Any] | None = None) -> None:
    payload = {
        "state": state,
        "updated_at": _utc_now(),
        "details": details or {},
    }
    write_json(run_book_dir / "run_state.json", payload)


def cmd_scan(args: argparse.Namespace) -> int:
    runs_root = Path(args.runs_root)
    fixtures_root = Path(args.fixtures_root)
    run_id = args.run_id or _run_id()
    book_id = args.book_id

    if args.clean_book:
        _archive_book_outputs(runs_root, book_id)

    run_book_dir, artifacts_dir, _ = _ensure_run_dirs(runs_root, run_id, book_id)

    source_raw = fixtures_root / book_id / "source_raw"
    files = sorted_source_files(source_raw)
    manifest = build_book_manifest(source_raw)
    signals = scan_book_html(files)

    write_json(
        artifacts_dir / "manifest.json",
        {
            "book_id": book_id,
            "source_raw": str(source_raw),
            "file_count": len(manifest),
            "files": manifest_as_jsonable(manifest),
        },
    )
    write_json(artifacts_dir / "bookcatcher.scan.json", scan_signals_jsonable(signals))

    _write_run_state(
        run_book_dir,
        "SCANNED",
        {
            "book_id": book_id,
            "run_id": run_id,
            "source_files": len(files),
        },
    )
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    runs_root = Path(args.runs_root)
    fixtures_root = Path(args.fixtures_root)
    must_not_path = Path(args.must_not_path)
    run_id = args.run_id or _run_id()
    book_id = args.book_id

    if args.clean_book:
        _archive_book_outputs(runs_root, book_id)

    run_book_dir, artifacts_dir, _ = _ensure_run_dirs(runs_root, run_id, book_id)

    source_raw = fixtures_root / book_id / "source_raw"
    files = sorted_source_files(source_raw)
    if not files:
        raise FileNotFoundError(f"No HTML files found under: {source_raw}")

    manifest = build_book_manifest(source_raw)
    write_json(
        artifacts_dir / "manifest.json",
        {
            "book_id": book_id,
            "source_raw": str(source_raw),
            "file_count": len(manifest),
            "files": manifest_as_jsonable(manifest),
        },
    )

    signals = scan_book_html(files)
    write_json(artifacts_dir / "bookcatcher.scan.json", scan_signals_jsonable(signals))

    must_not = _load_must_not(must_not_path)

    candidates = []
    for path in files:
        candidates.extend(extract_layer_a_candidates(path))
    scored = score_candidates(candidates, signals)
    score_map = {row.candidate_id: row for row in scored}

    heading_rows: list[dict[str, Any]] = []
    proposed_lines: list[str] = []

    for idx, cand in enumerate(candidates, start=1):
        score = score_map[cand.candidate_id]
        normalized = _normalize_text(cand.text)
        blocked = normalized in must_not
        is_heading = bool(score.suggested_is_heading and not blocked)
        level = max(2, min(6, score.suggested_level))
        heading_line = f"{'#' * level} {cand.text}"

        row = {
            **asdict(cand),
            "item_id": _item_id(asdict(cand), idx, "heading"),
            "score": score.score,
            "suggested": asdict(score),
            "proposal": "inject_heading" if is_heading else "skip",
            "review_required": True,
            "strict_anchor_eligible": is_heading,
            "is_heading": is_heading,
            "blocked_reason": "blocked_by_must_not_heading" if blocked else None,
            "proposed_markdown_heading": heading_line if is_heading else None,
            "topic_family_hint": "Exercises/Applications" if _is_exercise_text(cand.text) else None,
        }
        heading_rows.append(row)
        if is_heading:
            proposed_lines.append(heading_line)

    write_jsonl(artifacts_dir / "heading_injections.proposed.jsonl", heading_rows)

    chunk_plan = build_strict_anchor_boundaries(book_id=book_id, proposed_heading_lines=proposed_lines)
    chunk_items = []
    for idx, boundary in enumerate(chunk_plan.boundaries, start=1):
        item = asdict(boundary)
        item["item_id"] = _item_id(item, idx, "chunk")
        item["review_required"] = True
        chunk_items.append(item)

    chunk_payload = {
        "book_id": book_id,
        "strict_anchor_policy": STRICT_ANCHOR_REGEX,
        "approval_required": True,
        "status": "proposed",
        "items": chunk_items,
    }
    write_json(artifacts_dir / "chunk_plan.proposed.json", chunk_payload)
    (artifacts_dir / "chunk_plan.proposed.md").write_text(chunk_plan_markdown(chunk_plan), encoding="utf-8")

    anchor_before = len(candidates)
    anchor_after = max(anchor_before - sum(1 for r in heading_rows if r["proposal"] == "inject_heading"), 0)
    write_json(
        artifacts_dir / "proposal.metrics.json",
        {
            "anchor_miss_before": anchor_before,
            "anchor_miss_after_estimate": anchor_after,
            "anchor_miss_relative_reduction_estimate": 0.0 if anchor_before == 0 else (anchor_before - anchor_after) / anchor_before,
            "must_not_blocked": sum(1 for r in heading_rows if r.get("blocked_reason")),
        },
    )

    _write_run_state(
        run_book_dir,
        "PROPOSED_REVIEW_REQUIRED",
        {
            "book_id": book_id,
            "run_id": run_id,
            "heading_items": len(heading_rows),
            "chunk_items": len(chunk_items),
            "approval_required": True,
        },
    )

    return 0


def _summary_markdown(summary: ReviewSummary) -> str:
    lines = [
        "# Review summary",
        "",
        f"- run_id: `{summary.run_id}`",
        f"- book_id: `{summary.book_id}`",
        f"- resolved: `{summary.resolved}`",
        f"- approved: `{summary.approved}`",
        f"- edited: `{summary.edited}`",
        f"- rejected: `{summary.rejected}`",
        f"- blocked: `{summary.blocked}`",
        f"- downstream_apply_permitted: `{str(summary.downstream_apply_permitted).lower()}`",
    ]
    if summary.blocked_items:
        lines.append("")
        lines.append("## Blocked items")
        lines.extend(f"- `{item}`" for item in summary.blocked_items)
    lines.append("")
    return "\n".join(lines)


def cmd_approve(args: argparse.Namespace) -> int:
    run_book_dir = Path(args.runs_root) / args.run_id / args.book_id
    artifacts_dir = run_book_dir / "artifacts"

    heading_proposed_path = artifacts_dir / "heading_injections.proposed.jsonl"
    chunk_proposed_path = artifacts_dir / "chunk_plan.proposed.json"
    decisions_path = artifacts_dir / "review.decisions.jsonl"

    if not heading_proposed_path.exists() or not chunk_proposed_path.exists():
        raise FileNotFoundError("Missing proposed artifacts; run ibp propose first")

    heading_rows = read_jsonl(heading_proposed_path)
    chunk_payload = json.loads(chunk_proposed_path.read_text(encoding="utf-8"))
    chunk_rows = list(chunk_payload.get("items", []))

    decisions: list[DecisionRecord] = []

    if args.approve_all or args.reject_all:
        action = DecisionAction.APPROVE if args.approve_all else DecisionAction.REJECT
        for idx, row in enumerate(heading_rows, start=1):
            decisions.append(
                DecisionRecord.new(
                    artifact="heading_injections",
                    item_id=_item_id(row, idx, "heading"),
                    decision=action,
                    reviewer=args.reviewer,
                    reason="bulk decision via CLI",
                )
            )
        for idx, row in enumerate(chunk_rows, start=1):
            decisions.append(
                DecisionRecord.new(
                    artifact="chunk_plan",
                    item_id=_item_id(row, idx, "chunk"),
                    decision=action,
                    reviewer=args.reviewer,
                    reason="bulk decision via CLI",
                )
            )
        write_jsonl(decisions_path, [d.to_dict() for d in decisions])
    else:
        if not decisions_path.exists():
            raise FileNotFoundError(
                "No review decisions found. Provide --approve-all/--reject-all or create artifacts/review.decisions.jsonl"
            )
        decisions = [DecisionRecord.from_dict(row) for row in read_jsonl(decisions_path)]

    decision_map = {(d.artifact, d.item_id): d for d in decisions}
    summary = ReviewSummary(run_id=args.run_id, book_id=args.book_id)

    approved_headings: list[dict[str, Any]] = []
    approved_chunks: list[dict[str, Any]] = []

    for idx, row in enumerate(heading_rows, start=1):
        item_id = _item_id(row, idx, "heading")
        decision = decision_map.get(("heading_injections", item_id))
        if decision is None:
            summary.blocked += 1
            summary.blocked_items.append(f"heading_injections:{item_id}")
            continue
        summary.resolved += 1
        if decision.decision is DecisionAction.APPROVE:
            summary.approved += 1
            out = dict(row)
            out.update({"approved": True, "reviewer": decision.reviewer, "review_reason": decision.reason})
            approved_headings.append(out)
        elif decision.decision is DecisionAction.EDIT:
            summary.edited += 1
            edited = dict(row)
            if decision.edited_value:
                edited.update(decision.edited_value)
                edited["approved"] = True
                approved_headings.append(edited)
            else:
                summary.blocked += 1
                summary.blocked_items.append(f"heading_injections:{item_id}:missing_edit_payload")
        else:
            summary.rejected += 1

    for idx, row in enumerate(chunk_rows, start=1):
        item_id = _item_id(row, idx, "chunk")
        decision = decision_map.get(("chunk_plan", item_id))
        if decision is None:
            summary.blocked += 1
            summary.blocked_items.append(f"chunk_plan:{item_id}")
            continue
        summary.resolved += 1
        if decision.decision is DecisionAction.APPROVE:
            summary.approved += 1
            approved_chunks.append(row)
        elif decision.decision is DecisionAction.EDIT:
            summary.edited += 1
            edited = dict(row)
            if decision.edited_value:
                edited.update(decision.edited_value)
                approved_chunks.append(edited)
            else:
                summary.blocked += 1
                summary.blocked_items.append(f"chunk_plan:{item_id}:missing_edit_payload")
        else:
            summary.rejected += 1

    (artifacts_dir / "review_summary.md").write_text(_summary_markdown(summary), encoding="utf-8")

    if summary.blocked > 0:
        _write_run_state(run_book_dir, "REVIEW_BLOCKED", {"blocked": summary.blocked})
        return 3

    write_jsonl(artifacts_dir / "heading_injections.approved.jsonl", approved_headings)
    chunk_payload["items"] = approved_chunks
    chunk_payload["status"] = "approved"
    chunk_payload["approval_required"] = False
    write_json(artifacts_dir / "chunk_plan.approved.json", chunk_payload)

    proposal_metrics = json.loads((artifacts_dir / "proposal.metrics.json").read_text(encoding="utf-8"))
    write_run_report(
        run_id=args.run_id,
        book_id=args.book_id,
        anchor_miss_before=int(proposal_metrics.get("anchor_miss_before", 0)),
        anchor_miss_after=int(proposal_metrics.get("anchor_miss_after_estimate", 0)),
        decision_rows=approved_headings,
        output_root=Path(args.runs_root),
        minimum_relative_reduction=args.minimum_relative_reduction,
        fail_on_guardrails=False,
    )

    _write_run_state(run_book_dir, "APPROVED", {"approved_headings": len(approved_headings), "approved_chunks": len(approved_chunks)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ibp", description="Islamic Book Processor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Deterministic scan only")
    scan.add_argument("book_id")
    scan.add_argument("--fixtures-root", default="fixtures/shamela_exports")
    scan.add_argument("--runs-root", default="runs")
    scan.add_argument("--run-id")
    scan.add_argument("--clean-book", action="store_true")
    scan.set_defaults(func=cmd_scan)

    propose = subparsers.add_parser("propose", help="Generate proposed heading injections and chunk plan")
    propose.add_argument("--book-id", required=True)
    propose.add_argument("--fixtures-root", default="fixtures/shamela_exports")
    propose.add_argument("--must-not-path", default="training/gold_snippets/must_not_heading.jsonl")
    propose.add_argument("--runs-root", default="runs")
    propose.add_argument("--run-id")
    propose.add_argument("--clean-book", action="store_true")
    propose.set_defaults(func=cmd_propose)

    approve = subparsers.add_parser("approve", help="Approve/reject proposed artifacts")
    approve.add_argument("--runs-root", default="runs")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--book-id", required=True)
    approve.add_argument("--approve-all", action="store_true")
    approve.add_argument("--reject-all", action="store_true")
    approve.add_argument("--reviewer", default="human")
    approve.add_argument("--minimum-relative-reduction", type=float, default=0.0)
    approve.set_defaults(func=cmd_approve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "approve_all", False) and getattr(args, "reject_all", False):
        parser.error("--approve-all and --reject-all are mutually exclusive")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
