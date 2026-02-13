"""Topic placement engine based on heading/body similarity against topic exemplars."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


@dataclass(frozen=True)
class PlacementCandidate:
    topic_id: str
    score: float
    heading_similarity: float
    body_similarity: float
    title_similarity: float
    exemplar_similarity: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class PlacementDecision:
    status: str
    chosen_topic_id: str | None
    confidence: float
    reasons: tuple[str, ...]
    candidates: tuple[PlacementCandidate, ...]


@dataclass(frozen=True)
class _ExemplarFeatures:
    heading_tokens: set[str]
    body_tokens: set[str]


def _tokenize(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.findall((text or "").lower()) if tok}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = left.intersection(right)
    union = left.union(right)
    if not union:
        return 0.0
    return len(inter) / len(union)


def _iter_exemplars(topic: dict[str, Any]) -> list[dict[str, str]]:
    exemplars = topic.get("exemplars")
    if isinstance(exemplars, list) and exemplars:
        return [e for e in exemplars if isinstance(e, dict)]

    canonical_chunks = topic.get("canonical_chunks")
    if isinstance(canonical_chunks, list) and canonical_chunks:
        return [e for e in canonical_chunks if isinstance(e, dict)]

    return [{"heading": topic.get("title", ""), "body": topic.get("description", "")}]


def _topic_title_text(topic: dict[str, Any]) -> str:
    title_parts: list[str] = []
    for key in ("title", "display_title_ar", "display_title_en"):
        value = topic.get(key)
        if isinstance(value, str) and value.strip():
            title_parts.append(value)

    aliases = topic.get("aliases")
    if isinstance(aliases, list):
        title_parts.extend(str(alias) for alias in aliases if isinstance(alias, str) and alias.strip())
    return " ".join(title_parts)


def _build_topic_lexicon(topic: dict[str, Any]) -> tuple[set[str], list[_ExemplarFeatures]]:
    title_tokens = _tokenize(_topic_title_text(topic))
    exemplar_features: list[_ExemplarFeatures] = []

    for exemplar in _iter_exemplars(topic):
        heading_tokens = _tokenize(exemplar.get("heading", ""))
        body_tokens = _tokenize(exemplar.get("body", ""))
        title_tokens.update(heading_tokens)
        exemplar_features.append(_ExemplarFeatures(heading_tokens=heading_tokens, body_tokens=body_tokens))

    return title_tokens, exemplar_features


def _top_overlaps(chunk_tokens: set[str], topic_tokens: set[str], *, limit: int = 5) -> tuple[str, ...]:
    overlap = sorted(chunk_tokens.intersection(topic_tokens))
    return tuple(overlap[:limit])


def _score_topic(chunk_heading: str, chunk_body: str, topic: dict[str, Any]) -> PlacementCandidate | None:
    topic_id = topic.get("topic_id")
    if not isinstance(topic_id, str) or not topic_id.strip():
        return None

    heading_tokens = _tokenize(chunk_heading)
    body_tokens = _tokenize(chunk_body)

    title_tokens, exemplar_features = _build_topic_lexicon(topic)
    title_similarity = _jaccard(heading_tokens, title_tokens)

    best_heading = 0.0
    best_body = 0.0
    best_exemplar = 0.0

    for exemplar in exemplar_features:
        heading_similarity = _jaccard(heading_tokens, exemplar.heading_tokens)
        body_similarity = _jaccard(body_tokens, exemplar.body_tokens)
        combined = (0.5 * heading_similarity) + (0.5 * body_similarity)
        best_heading = max(best_heading, heading_similarity)
        best_body = max(best_body, body_similarity)
        best_exemplar = max(best_exemplar, combined)

    score = (0.45 * best_heading) + (0.25 * best_body) + (0.2 * title_similarity) + (0.1 * best_exemplar)

    heading_overlap = _top_overlaps(heading_tokens, title_tokens)
    body_overlap = _top_overlaps(body_tokens, set().union(*(e.body_tokens for e in exemplar_features)))
    evidence = (
        f"heading_overlap={','.join(heading_overlap) or 'none'}",
        f"body_overlap={','.join(body_overlap) or 'none'}",
        f"title_similarity={title_similarity:.3f}",
        f"exemplar_similarity={best_exemplar:.3f}",
    )

    return PlacementCandidate(
        topic_id=topic_id,
        score=score,
        heading_similarity=best_heading,
        body_similarity=best_body,
        title_similarity=title_similarity,
        exemplar_similarity=best_exemplar,
        evidence=evidence,
    )


def place_chunk(
    *,
    chunk_heading: str,
    chunk_body: str,
    topics: list[dict[str, Any]],
    min_confidence: float = 0.55,
    ambiguity_margin: float = 0.08,
    max_candidates: int = 3,
) -> PlacementDecision:
    """Place one chunk against a topic registry.

    Uses only stable topic identities from registry `topic_id`.
    """

    candidates = [
        scored
        for topic in topics
        if (scored := _score_topic(chunk_heading=chunk_heading, chunk_body=chunk_body, topic=topic)) is not None
    ]
    candidates.sort(key=lambda row: row.score, reverse=True)
    shortlist = tuple(candidates[:max_candidates])

    if not shortlist:
        return PlacementDecision(
            status="review",
            chosen_topic_id=None,
            confidence=0.0,
            reasons=("no_existing_topics",),
            candidates=shortlist,
        )

    top = shortlist[0]
    reasons: list[str] = []

    if top.score < min_confidence:
        reasons.append("confidence_below_threshold")

    if len(shortlist) > 1 and (top.score - shortlist[1].score) < ambiguity_margin:
        reasons.append("ambiguous_top_candidates")

    if reasons:
        return PlacementDecision(
            status="review",
            chosen_topic_id=None,
            confidence=top.score,
            reasons=tuple(reasons),
            candidates=shortlist,
        )

    return PlacementDecision(
        status="assigned",
        chosen_topic_id=top.topic_id,
        confidence=top.score,
        reasons=(),
        candidates=shortlist,
    )


def decision_as_jsonable(decision: PlacementDecision) -> dict[str, Any]:
    return {
        "status": decision.status,
        "chosen_topic_id": decision.chosen_topic_id,
        "confidence": round(decision.confidence, 6),
        "reasons": list(decision.reasons),
        "candidate_alternatives": [
            {
                "topic_id": c.topic_id,
                "score": round(c.score, 6),
                "heading_similarity": round(c.heading_similarity, 6),
                "body_similarity": round(c.body_similarity, 6),
                "title_similarity": round(c.title_similarity, 6),
                "exemplar_similarity": round(c.exemplar_similarity, 6),
                "evidence": list(c.evidence),
            }
            for c in decision.candidates
        ],
    }
