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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ibp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    approve = subparsers.add_parser("approve", help="Approve or block proposed review artifacts")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--book-id", required=True)
    approve.add_argument("--from", dest="source_tag", default="proposed")
    approve.add_argument("--out", dest="out_tag", default="approved")
    approve.set_defaults(func=run_approve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
