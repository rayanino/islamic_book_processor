"""Deterministic QA metrics for heading injection runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class AnchorMissMetrics:
    before: int
    after: int
    relative_reduction: float


@dataclass(frozen=True)
class SplitFalsePositiveMetrics:
    split_name: str
    negative_total: int
    false_positives: int
    fp_rate: float


@dataclass(frozen=True)
class MustNotHeadingViolation:
    candidate_id: str
    text: str
    signature: str
    reason: str


@dataclass(frozen=True)
class InjectionTraceabilityRow:
    candidate_id: str
    signature: str
    excerpt: str
    score: float | None
    markdown_location: str
    approved: bool


@dataclass(frozen=True)
class QAMetricsBundle:
    anchor: AnchorMissMetrics
    must_not_heading_violations: list[MustNotHeadingViolation]
    train_fp: SplitFalsePositiveMetrics
    holdout_fp: SplitFalsePositiveMetrics
    holdout_regression: bool
    injection_traceability: list[InjectionTraceabilityRow]
    guardrail_violations: list[str]


class GuardrailViolationError(RuntimeError):
    """Raised when mandatory QA guardrails are violated."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def compute_anchor_metrics(anchor_miss_before: int, anchor_miss_after: int) -> AnchorMissMetrics:
    if anchor_miss_before < 0 or anchor_miss_after < 0:
        raise ValueError("anchor_miss values must be >= 0")

    if anchor_miss_before == 0:
        reduction = 0.0 if anchor_miss_after == 0 else -1.0
    else:
        reduction = (anchor_miss_before - anchor_miss_after) / anchor_miss_before

    return AnchorMissMetrics(
        before=anchor_miss_before,
        after=anchor_miss_after,
        relative_reduction=reduction,
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "approved", "allow"}
    return False


def _is_predicted_heading(record: dict[str, Any]) -> bool:
    if _coerce_bool(record.get("is_heading")):
        return True
    if _coerce_bool(record.get("injected")):
        return True

    for key in ("decision", "suggested", "prediction"):
        nested = record.get(key)
        if isinstance(nested, dict) and _coerce_bool(nested.get("is_heading")):
            return True

    return False


def _has_explicit_approval(record: dict[str, Any]) -> bool:
    approval_keys = (
        "approved",
        "review_approved",
        "human_approved",
        "explicit_approval",
        "approval_granted",
    )
    return any(_coerce_bool(record.get(key)) for key in approval_keys)


def _decision_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for record in records:
        candidate_id = record.get("candidate_id")
        if candidate_id:
            mapped[str(candidate_id)] = record
    return mapped


def compute_must_not_heading_violations(
    must_not_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
) -> list[MustNotHeadingViolation]:
    decisions = _decision_map(decision_rows)
    violations: list[MustNotHeadingViolation] = []

    for row in must_not_rows:
        candidate_id = str(row.get("candidate_id", ""))
        if not candidate_id:
            continue

        decision = decisions.get(candidate_id)
        if decision is None:
            continue

        if _is_predicted_heading(decision) and not _has_explicit_approval(decision):
            violations.append(
                MustNotHeadingViolation(
                    candidate_id=candidate_id,
                    text=str(row.get("text", "")),
                    signature=str(row.get("signature", "")),
                    reason="blocked by must-not-heading (predicted heading without explicit approval)",
                )
            )

    return violations


def _compute_fp_for_split(
    split_name: str,
    split_rows: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
) -> SplitFalsePositiveMetrics:
    negatives = [r for r in split_rows if not _coerce_bool(r.get("gold", {}).get("is_heading"))]
    negative_total = len(negatives)

    false_positives = 0
    for row in negatives:
        candidate_id = str(row.get("candidate_id", ""))
        decision = decisions.get(candidate_id)
        if decision and _is_predicted_heading(decision):
            false_positives += 1

    fp_rate = (false_positives / negative_total) if negative_total else 0.0
    return SplitFalsePositiveMetrics(
        split_name=split_name,
        negative_total=negative_total,
        false_positives=false_positives,
        fp_rate=fp_rate,
    )


def compute_holdout_train_fp(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
) -> tuple[SplitFalsePositiveMetrics, SplitFalsePositiveMetrics, bool]:
    decisions = _decision_map(decision_rows)
    train_fp = _compute_fp_for_split("train", train_rows, decisions)
    holdout_fp = _compute_fp_for_split("holdout", holdout_rows, decisions)
    return train_fp, holdout_fp, holdout_fp.fp_rate > train_fp.fp_rate


def _extract_markdown_location(record: dict[str, Any]) -> str:
    location = record.get("markdown_location")
    if isinstance(location, str) and location:
        return location
    if isinstance(location, dict):
        file_part = location.get("file") or location.get("path") or "unknown.md"
        start = location.get("line_start")
        end = location.get("line_end")
        if start is not None and end is not None:
            return f"{file_part}:{start}-{end}"
        if start is not None:
            return f"{file_part}:{start}"
    path = record.get("derived_markdown_path") or record.get("markdown_path") or "unknown.md"
    line = record.get("line") or record.get("line_start")
    if line is not None:
        return f"{path}:{line}"
    return str(path)


def compute_traceability_rows(decision_rows: list[dict[str, Any]]) -> list[InjectionTraceabilityRow]:
    rows: list[InjectionTraceabilityRow] = []
    for record in decision_rows:
        if not _is_predicted_heading(record):
            continue

        candidate_id = str(record.get("candidate_id", ""))
        signature = str(record.get("signature") or record.get("candidate_signature") or "")
        excerpt = str(record.get("html_excerpt") or record.get("excerpt") or record.get("text") or "")
        score_raw = record.get("score")
        if score_raw is None and isinstance(record.get("suggested"), dict):
            score_raw = record["suggested"].get("confidence")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else None

        rows.append(
            InjectionTraceabilityRow(
                candidate_id=candidate_id,
                signature=signature,
                excerpt=excerpt,
                score=score,
                markdown_location=_extract_markdown_location(record),
                approved=_has_explicit_approval(record),
            )
        )

    return rows


def compute_qa_metrics(
    *,
    anchor_miss_before: int,
    anchor_miss_after: int,
    must_not_rows: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
    minimum_relative_reduction: float = 0.0,
) -> QAMetricsBundle:
    anchor = compute_anchor_metrics(anchor_miss_before, anchor_miss_after)
    must_not_violations = compute_must_not_heading_violations(must_not_rows, decision_rows)
    train_fp, holdout_fp, holdout_regression = compute_holdout_train_fp(train_rows, holdout_rows, decision_rows)
    traceability = compute_traceability_rows(decision_rows)

    guardrail_violations: list[str] = []
    if anchor.after >= anchor.before:
        guardrail_violations.append("anchor_miss_after must be lower than anchor_miss_before")
    if anchor.relative_reduction < minimum_relative_reduction:
        guardrail_violations.append(
            f"anchor miss relative reduction {anchor.relative_reduction:.4f} is below minimum {minimum_relative_reduction:.4f}"
        )
    if must_not_violations:
        guardrail_violations.append(
            f"must-not-heading false positives detected without approval: {len(must_not_violations)}"
        )
    if holdout_regression:
        guardrail_violations.append(
            f"holdout FP rate regression: holdout={holdout_fp.fp_rate:.4f} train={train_fp.fp_rate:.4f}"
        )

    return QAMetricsBundle(
        anchor=anchor,
        must_not_heading_violations=must_not_violations,
        train_fp=train_fp,
        holdout_fp=holdout_fp,
        holdout_regression=holdout_regression,
        injection_traceability=traceability,
        guardrail_violations=guardrail_violations,
    )
