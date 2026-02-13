from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict

STRICT_ANCHOR_RE = re.compile(r"^#{2,6}\s+")


@dataclass(frozen=True)
class ChunkBoundary:
    anchor: str
    level: int
    heading: str
    start_anchor_index: int


@dataclass(frozen=True)
class ChunkPlan:
    book_id: str
    strict_anchor_policy: str
    boundaries: list[ChunkBoundary]
    approval_required: bool
    status: str


def build_strict_anchor_boundaries(book_id: str, proposed_heading_lines: list[str]) -> ChunkPlan:
    boundaries: list[ChunkBoundary] = []
    for idx, line in enumerate(proposed_heading_lines):
        if not STRICT_ANCHOR_RE.match(line):
            continue
        marks = line.split(" ", 1)[0]
        title = line[len(marks):].strip()
        anchor = hashlib.sha256(f"{book_id}|{idx}|{line}".encode("utf-8")).hexdigest()[:16]
        boundaries.append(
            ChunkBoundary(
                anchor=anchor,
                level=len(marks),
                heading=title,
                start_anchor_index=idx,
            )
        )

    return ChunkPlan(
        book_id=book_id,
        strict_anchor_policy=STRICT_ANCHOR_RE.pattern,
        boundaries=boundaries,
        approval_required=True,
        status="approval required",
    )


def chunk_plan_json(plan: ChunkPlan) -> str:
    return json.dumps(
        {
            "book_id": plan.book_id,
            "strict_anchor_policy": plan.strict_anchor_policy,
            "approval_required": plan.approval_required,
            "status": plan.status,
            "boundaries": [asdict(b) for b in plan.boundaries],
        },
        ensure_ascii=False,
        indent=2,
    )


def chunk_plan_markdown(plan: ChunkPlan) -> str:
    lines = [
        f"# Chunk Plan Proposal — {plan.book_id}",
        "",
        f"Status: **{plan.status}**",
        f"Strict anchor policy: `{plan.strict_anchor_policy}`",
        "",
        "## Proposed chunk boundaries",
    ]
    if not plan.boundaries:
        lines.append("- No eligible anchors found under strict policy.")
    else:
        for b in plan.boundaries:
            lines.append(f"- `{b.anchor}` | H{b.level} | {b.heading}")
    lines.append("")
    lines.append("Approval is required before any apply stage.")
    return "\n".join(lines)
