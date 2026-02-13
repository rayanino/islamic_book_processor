"""Run report emitters for QA metrics and guardrail status."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from .metrics import GuardrailViolationError, QAMetricsBundle, compute_qa_metrics, load_jsonl


DEFAULT_MUST_NOT_PATH = Path("training/gold_snippets/must_not_heading.jsonl")
DEFAULT_TRAIN_PATH = Path("training/gold_snippets/splits/train.jsonl")
DEFAULT_HOLDOUT_PATH = Path("training/gold_snippets/splits/holdout.jsonl")


def _build_markdown_report(run_id: str, book_id: str, metrics: QAMetricsBundle) -> str:
    status = "FAILED" if metrics.guardrail_violations else "PASSED"
    lines = [
        f"# Run report: {run_id} / {book_id}",
        "",
        f"- Status: **{status}**",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Anchor miss",
        f"- before: `{metrics.anchor.before}`",
        f"- after: `{metrics.anchor.after}`",
        f"- relative reduction: `{metrics.anchor.relative_reduction:.4f}`",
        "",
        "## Must-not-heading guardrail",
        f"- violations without approval: `{len(metrics.must_not_heading_violations)}`",
    ]

    if metrics.must_not_heading_violations:
        lines.append("")
        lines.append("### Violations")
        for violation in metrics.must_not_heading_violations:
            lines.append(
                f"- `{violation.candidate_id}` | `{violation.signature}` | {violation.reason} | {violation.text}"
            )

    lines.extend(
        [
            "",
            "## False-positive comparison",
            f"- train fp: `{metrics.train_fp.false_positives}/{metrics.train_fp.negative_total}` (rate `{metrics.train_fp.fp_rate:.4f}`)",
            f"- holdout fp: `{metrics.holdout_fp.false_positives}/{metrics.holdout_fp.negative_total}` (rate `{metrics.holdout_fp.fp_rate:.4f}`)",
            f"- holdout regression: `{metrics.holdout_regression}`",
            "",
            "## Per-injection traceability",
            "| candidate_id | approved | score | signature | markdown_location | excerpt |",
            "|---|---:|---:|---|---|---|",
        ]
    )

    for row in metrics.injection_traceability:
        excerpt = row.excerpt.replace("|", "\\|").replace("\n", " ").strip()
        lines.append(
            f"| `{row.candidate_id}` | `{row.approved}` | `{'' if row.score is None else f'{row.score:.4f}'}` | `{row.signature}` | `{row.markdown_location}` | {excerpt} |"
        )

    if metrics.guardrail_violations:
        lines.extend(["", "## Guardrail violations"])
        for violation in metrics.guardrail_violations:
            lines.append(f"- {violation}")

    return "\n".join(lines) + "\n"


def _build_json_report(
    run_id: str,
    book_id: str,
    metrics: QAMetricsBundle,
    *,
    anchor_measurement_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = "failed" if metrics.guardrail_violations else "passed"
    return {
        "run_id": run_id,
        "book_id": book_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "metrics": {
            "anchor_miss_before": metrics.anchor.before,
            "anchor_miss_after": metrics.anchor.after,
            "anchor_miss_relative_reduction": metrics.anchor.relative_reduction,
            "anchor_measurement": anchor_measurement_metadata or {},
            "must_not_heading_violations": [asdict(item) for item in metrics.must_not_heading_violations],
            "must_not_heading_violations_count": len(metrics.must_not_heading_violations),
            "false_positive": {
                "train": asdict(metrics.train_fp),
                "holdout": asdict(metrics.holdout_fp),
                "holdout_regression": metrics.holdout_regression,
            },
            "injection_traceability": [asdict(item) for item in metrics.injection_traceability],
        },
        "guardrail_violations": metrics.guardrail_violations,
    }


def write_run_report(
    *,
    run_id: str,
    book_id: str,
    anchor_miss_before: int,
    anchor_miss_after: int,
    decision_rows: list[dict[str, Any]],
    output_root: Path = Path("runs"),
    must_not_path: Path = DEFAULT_MUST_NOT_PATH,
    train_path: Path = DEFAULT_TRAIN_PATH,
    holdout_path: Path = DEFAULT_HOLDOUT_PATH,
    minimum_relative_reduction: float = 0.0,
    anchor_measurement_metadata: dict[str, Any] | None = None,
    fail_on_guardrails: bool = True,
) -> tuple[Path, Path, dict[str, Any]]:
    metrics = compute_qa_metrics(
        anchor_miss_before=anchor_miss_before,
        anchor_miss_after=anchor_miss_after,
        must_not_rows=load_jsonl(must_not_path),
        train_rows=load_jsonl(train_path),
        holdout_rows=load_jsonl(holdout_path),
        decision_rows=decision_rows,
        minimum_relative_reduction=minimum_relative_reduction,
    )

    report_dir = output_root / run_id / book_id
    report_dir.mkdir(parents=True, exist_ok=True)
    json_report_path = report_dir / "run_report.json"
    md_report_path = report_dir / "run_report.md"

    report_payload = _build_json_report(run_id, book_id, metrics, anchor_measurement_metadata=anchor_measurement_metadata)
    markdown_report = _build_markdown_report(run_id, book_id, metrics)

    json_report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_report_path.write_text(markdown_report, encoding="utf-8")

    if fail_on_guardrails and metrics.guardrail_violations:
        raise GuardrailViolationError(
            "Mandatory guardrails violated; run status is failed. "
            + " | ".join(metrics.guardrail_violations)
        )

    return json_report_path, md_report_path, report_payload
