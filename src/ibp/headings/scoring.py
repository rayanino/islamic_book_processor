from __future__ import annotations

from dataclasses import dataclass, asdict

from ibp.bookcatcher.scan import ScanSignals
from ibp.headings.candidates import HeadingCandidate


@dataclass(frozen=True)
class ScoredHeading:
    candidate_id: str
    score: float
    suggested_is_heading: bool
    suggested_level: int
    suggested_reason: str
    suggested_confidence: float
    rationale: list[str]


def score_candidate(candidate: HeadingCandidate, signals: ScanSignals) -> ScoredHeading:
    score = 0.0
    rationale: list[str] = []

    if candidate.kind == "title":
        score += 0.35
        rationale.append("title_kind")
    if any(tok in candidate.text for tok in ("باب", "فصل", "كتاب", "مقدمة", "خاتمة")):
        score += 0.25
        rationale.append("arabic_heading_cue")
    if len(candidate.text) <= 80:
        score += 0.1
        rationale.append("title_length")
    if candidate.text in signals.repeated_headers or candidate.text in signals.repeated_footers:
        score -= 0.5
        rationale.append("repeated_running_header_footer")
    if candidate.kind in {"metadata", "footnote", "pagehead"}:
        score -= 0.45
        rationale.append("non_structural_zone")

    score = max(0.0, min(1.0, score))
    is_heading = score >= 0.5
    level = 2
    if is_heading and any(tok in candidate.text for tok in ("فصل", "تنبيه", "مسألة")):
        level = 3
    reason = "deterministic_layer_b"

    return ScoredHeading(
        candidate_id=candidate.candidate_id,
        score=round(score, 4),
        suggested_is_heading=is_heading,
        suggested_level=level,
        suggested_reason=reason,
        suggested_confidence=round(score, 4),
        rationale=rationale,
    )


def score_candidates(candidates: list[HeadingCandidate], signals: ScanSignals) -> list[ScoredHeading]:
    return [score_candidate(c, signals) for c in candidates]


def scored_jsonable(items: list[ScoredHeading]) -> list[dict]:
    return [asdict(x) for x in items]
