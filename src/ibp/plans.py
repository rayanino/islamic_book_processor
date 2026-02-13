from __future__ import annotations

from pathlib import Path

from .utils import write_json


def write_chunk_plan(run_dir: Path, book_id: str, heading_summary: dict, scan_summary: dict) -> None:
    before = max(heading_summary["candidate_count"], 1)
    after = max(before - heading_summary["proposed_injection_count"], 0)
    rel_reduction = (before - after) / before

    payload = {
        "book_id": book_id,
        "status": "proposed",
        "approval_gate": "pending_human_review",
        "strict_anchor_regex": r"^#{2,6}\s+",
        "anchor_miss_before": before,
        "anchor_miss_after_estimate": after,
        "anchor_miss_relative_reduction_estimate": round(rel_reduction, 4),
        "proposed_heading_injections": heading_summary["proposed_injection_count"],
        "blocked_by_must_not_heading": heading_summary["blocked_by_must_not_count"],
        "taxonomy_proposals": [
            {
                "family": "Exercises/Applications",
                "status": "review_required",
                "trigger": "exercise-like heading candidate detected",
            }
        ],
        "book_catcher": scan_summary,
    }
    write_json(run_dir / "chunk_plan.proposed.json", payload)

    md = run_dir / "chunk_plan.proposed.md"
    md.write_text(
        "\n".join(
            [
                f"# Chunk Plan (Proposed) — {book_id}",
                "",
                "- Status: **PROPOSED** (no injections applied)",
                "- Approval gate: **required**",
                f"- Proposed heading injections: **{heading_summary['proposed_injection_count']}**",
                f"- Blocked by must_not_heading: **{heading_summary['blocked_by_must_not_count']}**",
                f"- Anchor misses (before): **{before}**",
                f"- Anchor misses (after estimate): **{after}**",
                f"- Relative reduction estimate: **{rel_reduction:.2%}**",
                "",
                "## Safety",
                "- Strict anchors only (`^#{2,6}\\s+`)",
                "- All heading injections are review-gated",
                "- No canonical writes performed in propose stage",
            ]
        ),
        encoding="utf-8",
    )
