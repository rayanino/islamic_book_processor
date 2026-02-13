"""Command line interface for the Islamic Book Processor."""


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
from ibp.placement.engine import decision_as_jsonable, place_chunk
from ibp.qa import GuardrailViolationError, write_run_report
from ibp.run_context import RunContext


STRICT_MARKDOWN_HEADING_PREFIXES = ("## ", "### ", "#### ", "##### ", "###### ")


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


def _split_by_strict_anchors(markdown_lines: list[str]) -> list[dict]:
    """Return strict heading candidates from markdown lines.

    This helper is used in propose only to suggest boundaries for human review.
    """

    items: list[dict] = []
    for line_number, line in enumerate(markdown_lines, start=1):
        stripped = line.strip()
        if not stripped.startswith(STRICT_MARKDOWN_HEADING_PREFIXES):
            continue
        marks = stripped.split(" ", 1)[0]
        heading = stripped[len(marks):].strip()
        items.append(
            {
                "line_number": line_number,
                "level": len(marks),
                "heading": heading,
            }
        )
    return items


def _approved_items(plan_payload: dict) -> list[dict]:
    items = plan_payload.get("items")
    if isinstance(items, list):
        return items
    boundaries = plan_payload.get("boundaries")
    if isinstance(boundaries, list):
        return boundaries
    return []


def _load_topic_registry(artifacts_dir: Path) -> list[dict]:
    for path in (
        artifacts_dir / "topic_registry.json",
        artifacts_dir / "registry" / "topics.json",
    ):
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        topics = payload.get("topics") if isinstance(payload, dict) else None
        if isinstance(topics, list):
            return topics
    return []


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _measure_anchor_miss_after(approved_items: list[dict], markdown_lines: list[str]) -> tuple[int, int]:
    strict_headings = _split_by_strict_anchors(markdown_lines)
    before = len(approved_items)
    misses = 0
    next_cursor = 0

    for approved in approved_items:
        expected_heading = (approved.get("heading") or approved.get("title") or approved.get("text") or "").strip()
        expected_level = approved.get("level")
        expected_line = approved.get("line_number") or approved.get("start_line")

        matched = False
        for idx in range(next_cursor, len(strict_headings)):
            candidate = strict_headings[idx]
            if expected_heading and candidate["heading"] != expected_heading:
                continue
            if expected_level and candidate["level"] != expected_level:
                continue
            if expected_line and candidate["line_number"] != expected_line:
                continue
            matched = True
            next_cursor = idx + 1
            break

        if not matched:
            misses += 1

    return before, misses


def _write_run_state(run_dir: Path, *, status: str, stage: str, failure_reasons: list[str] | None = None) -> None:
    payload = _read_json(run_dir / "run_state.json")
    payload.update(
        {
            "status": status,
            "stage": stage,
            "failure_reasons": failure_reasons or [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_json(run_dir / "run_state.json", payload)


def _write_run_report_status(run_dir: Path, *, book_id: str, run_id: str, status: str, failure_reasons: list[str]) -> None:
    payload = _read_json(run_dir / "run_report.json")
    payload.update(
        {
            "book_id": book_id,
            "run_id": run_id,
            "status": status,
            "failure_reasons": failure_reasons,
        }
    )
    _write_json(run_dir / "run_report.json", payload)


def cmd_scan(args: argparse.Namespace) -> int:
    runs_dir = getattr(args, "runs_root", None) or getattr(args, "runs_dir", "runs")
    ctx = RunContext.create(book_id=args.book_id, runs_dir=runs_dir)
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
    _write_json(
        ctx.artifacts_dir / "bookcatcher.scan.json",
        {
            "run_id": ctx.run_id,
            "book_id": ctx.book_id,
            "status": "completed",
            "signals": [],
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
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    files = sorted_source_files(source_raw)
    manifest = build_book_manifest(source_raw)
    _write_json(
        artifacts_dir / "manifest.json",
        {
            "book_id": book_id,
            "source_raw": str(source_raw),
            "file_count": len(manifest),
            "files": manifest_as_jsonable(manifest),
        },
    )

    signals = scan_book_html(files)
    _write_json(artifacts_dir / "bookcatcher.scan.json", scan_signals_jsonable(signals))

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

    _write_jsonl(artifacts_dir / "heading_injections.proposed.jsonl", heading_rows)
    _write_json(artifacts_dir / "heading_candidates.debug.json", {"items": candidates_jsonable(candidates)})
    _write_json(artifacts_dir / "heading_scores.debug.json", {"items": scored_jsonable(scored)})

    _split_by_strict_anchors(proposed_lines)
    plan = build_strict_anchor_boundaries(book_id=book_id, proposed_heading_lines=proposed_lines)
    (artifacts_dir / "chunk_plan.proposed.json").write_text(chunk_plan_json(plan) + "\n", encoding="utf-8")
    (artifacts_dir / "chunk_plan.proposed.md").write_text(chunk_plan_markdown(plan), encoding="utf-8")

    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs_root) / args.run_id / args.book_id
    artifacts_dir = run_dir / "artifacts"
    proposed = artifacts_dir / "heading_injections.proposed.jsonl"
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

    _write_jsonl(artifacts_dir / "heading_injections.approved.jsonl", approved_rows)

    proposed_plan = artifacts_dir / "chunk_plan.proposed.json"
    plan_payload = _read_json(proposed_plan)
    items = _approved_items(plan_payload)

    derived_book = run_dir / "derived" / "book.md"
    if not derived_book.exists():
        failure_reasons = [f"Missing derived markdown book: {derived_book}"]
        _write_run_report_status(
            run_dir,
            book_id=args.book_id,
            run_id=args.run_id,
            status="failed",
            failure_reasons=failure_reasons,
        )
        _write_run_state(run_dir, status="FAILED", stage="approve", failure_reasons=failure_reasons)
        return 1

    before, after = _measure_anchor_miss_after(items, derived_book.read_text(encoding="utf-8").splitlines())

    fail_on_guardrails = args.mode == "production"
    try:
        write_run_report(
            run_id=args.run_id,
            book_id=args.book_id,
            anchor_miss_before=before,
            anchor_miss_after=after,
            decision_rows=approved_rows,
            output_root=Path(args.runs_root),
            minimum_relative_reduction=args.minimum_relative_reduction,
            fail_on_guardrails=fail_on_guardrails,
        )
    except GuardrailViolationError:
        report_payload = _read_json(run_dir / "run_report.json")
        failure_reasons = report_payload.get("guardrail_violations") or ["Mandatory guardrails violated"]
        _write_run_report_status(
            run_dir,
            book_id=args.book_id,
            run_id=args.run_id,
            status="failed",
            failure_reasons=failure_reasons,
        )
        _write_run_state(run_dir, status="FAILED", stage="approve", failure_reasons=failure_reasons)
        return 1

    if proposed_plan.exists():
        _write_json(
            artifacts_dir / "chunk_plan.approved.json",
            {
                "book_id": args.book_id,
                "status": "approved",
                "items": items,
            },
        )
    _write_run_report_status(
        run_dir,
        book_id=args.book_id,
        run_id=args.run_id,
        status="approved",
        failure_reasons=[],
    )
    _write_run_state(run_dir, status="APPROVED", stage="approve", failure_reasons=[])
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs_root) / args.run_id / args.book_id
    artifacts_dir = run_dir / "artifacts"
    derived_book = run_dir / "derived" / "book.md"
    approved_path = artifacts_dir / "chunk_plan.approved.json"

    if not approved_path.exists():
        raise FileNotFoundError(f"Missing approved chunk plan: {approved_path}")
    if not derived_book.exists():
        raise FileNotFoundError(f"Missing derived markdown book: {derived_book}")

    plan_payload = json.loads(approved_path.read_text(encoding="utf-8"))
    approved_items = plan_payload.get("items")
    if not isinstance(approved_items, list):
        raise ValueError("Approved plan must contain an 'items' list")

    markdown_lines = derived_book.read_text(encoding="utf-8").splitlines()
    strict_headings = _split_by_strict_anchors(markdown_lines)
    topics = _load_topic_registry(artifacts_dir)

    mismatches: list[dict] = []
    matched_heading_indexes: list[int] = []
    next_cursor = 0
    for idx, approved in enumerate(approved_items):
        expected_heading = (approved.get("heading") or approved.get("title") or approved.get("text") or "").strip()
        expected_level = approved.get("level")
        expected_line = approved.get("line_number") or approved.get("start_line")

        match_index = None
        for i in range(next_cursor, len(strict_headings)):
            candidate = strict_headings[i]
            if expected_heading and candidate["heading"] != expected_heading:
                continue
            if expected_level and candidate["level"] != expected_level:
                continue
            if expected_line and candidate["line_number"] != expected_line:
                continue
            match_index = i
            break

        if match_index is None:
            mismatches.append(
                {
                    "approved_item_index": idx,
                    "approved_item": approved,
                    "reason": "approved boundary did not map to a strict markdown heading in derived/book.md",
                }
            )
            continue
        next_cursor = match_index + 1
        matched_heading_indexes.append(match_index)

    if mismatches:
        failure_reasons = [
            "approved boundary did not map to a strict markdown heading in derived/book.md",
        ]
        _write_json(
            artifacts_dir / "apply.boundary_mismatch.json",
            {
                "book_id": args.book_id,
                "run_id": args.run_id,
                "status": "failed_closed",
                "approved_item_count": len(approved_items),
                "strict_heading_count": len(strict_headings),
                "mismatches": mismatches,
            },
        )
        _write_run_report_status(
            run_dir,
            book_id=args.book_id,
            run_id=args.run_id,
            status="failed",
            failure_reasons=failure_reasons,
        )
        _write_run_state(run_dir, status="FAILED", stage="apply", failure_reasons=failure_reasons)
        return 1

    review_items: list[dict] = []
    placement_items: list[dict] = []
    for idx, approved in enumerate(approved_items):
        heading_index = matched_heading_indexes[idx]
        heading = strict_headings[heading_index]
        heading_line_index = heading["line_number"] - 1

        if idx + 1 < len(matched_heading_indexes):
            next_heading_line_index = strict_headings[matched_heading_indexes[idx + 1]]["line_number"] - 1
        else:
            next_heading_line_index = len(markdown_lines)

        body_lines = markdown_lines[heading_line_index + 1:next_heading_line_index]
        chunk_body = "\n".join(line for line in body_lines if line.strip())
        decision = place_chunk(
            chunk_heading=heading.get("heading", ""),
            chunk_body=chunk_body,
            topics=topics,
        )
        jsonable = decision_as_jsonable(decision)
        placement_payload = {
            "approved_item_index": idx,
            "approved_item": approved,
            "chunk_features": {
                "heading": heading.get("heading", ""),
                "body_excerpt": chunk_body[:500],
            },
            **jsonable,
        }
        placement_items.append(placement_payload)

        if decision.status == "review":
            review_items.append(
                {
                    "kind": "topic_placement",
                    "approved_item_index": idx,
                    "machine_reasons": jsonable["reasons"],
                    "candidate_alternatives": jsonable["candidate_alternatives"],
                    "chunk_features": placement_payload["chunk_features"],
                    "approved_item": approved,
                }
            )

    _write_json(
        artifacts_dir / "topic_placements.applied.json",
        {
            "book_id": args.book_id,
            "run_id": args.run_id,
            "topics_source": "artifacts/topic_registry.json#topics",
            "items": placement_items,
        },
    )

    if review_items:
        _write_json(
            run_dir / "_REVIEW" / "topic_placements.review.json",
            {
                "book_id": args.book_id,
                "run_id": args.run_id,
                "status": "review_required",
                "items": review_items,
            },
        )

    _write_json(
        artifacts_dir / "chunking.applied.json",
        {
            "book_id": args.book_id,
            "run_id": args.run_id,
            "status": "applied",
            "boundaries_source": "artifacts/chunk_plan.approved.json#items",
            "applied_items": approved_items,
            "topic_placement": {
                "status": "review_required" if review_items else "assigned",
                "review_count": len(review_items),
                "placements_source": "artifacts/topic_placements.applied.json#items",
            },
        },
    )

    approved_rows: list[dict] = []
    approved_rows_path = artifacts_dir / "heading_injections.approved.jsonl"
    if approved_rows_path.exists():
        for line in approved_rows_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                approved_rows.append(json.loads(line))

    before, after = _measure_anchor_miss_after(approved_items, markdown_lines)
    fail_on_guardrails = args.mode == "production"
    try:
        write_run_report(
            run_id=args.run_id,
            book_id=args.book_id,
            anchor_miss_before=before,
            anchor_miss_after=after,
            decision_rows=approved_rows,
            output_root=Path(args.runs_root),
            minimum_relative_reduction=args.minimum_relative_reduction,
            fail_on_guardrails=fail_on_guardrails,
        )
    except GuardrailViolationError:
        report_payload = _read_json(run_dir / "run_report.json")
        failure_reasons = report_payload.get("guardrail_violations") or ["Mandatory guardrails violated"]
        _write_run_report_status(
            run_dir,
            book_id=args.book_id,
            run_id=args.run_id,
            status="failed",
            failure_reasons=failure_reasons,
        )
        _write_run_state(run_dir, status="FAILED", stage="apply", failure_reasons=failure_reasons)
        return 1

    _write_run_report_status(
        run_dir,
        book_id=args.book_id,
        run_id=args.run_id,
        status="applied",
        failure_reasons=[],
    )
    _write_run_state(run_dir, status="APPLIED", stage="apply", failure_reasons=[])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ibp", description="Islamic Book Processor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Ingest + deterministic analysis")
    scan.add_argument("book_id")
    scan.add_argument("--runs-dir", default="runs")
    scan.add_argument("--runs-root")
    scan.add_argument("--fixtures-root")
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
    approve.add_argument("--reject-all", action="store_true")
    approve.add_argument("--reviewer", default="human")
    approve.add_argument("--minimum-relative-reduction", type=float, default=0.0)
    approve.add_argument("--mode", choices=["production", "development"], default="production")
    approve.set_defaults(func=cmd_approve)

    apply = subparsers.add_parser("apply", help="Apply approved chunk boundaries to derived markdown")
    apply.add_argument("--runs-root", default="runs")
    apply.add_argument("--run-id", required=True)
    apply.add_argument("--book-id", required=True)
    apply.add_argument("--minimum-relative-reduction", type=float, default=0.0)
    apply.add_argument("--mode", choices=["production", "development"], default="production")
    apply.set_defaults(func=cmd_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "approve_all", False) and getattr(args, "reject_all", False):
        parser.error("--approve-all and --reject-all are mutually exclusive")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
