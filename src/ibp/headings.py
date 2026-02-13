from __future__ import annotations

import json
import re
from pathlib import Path

from .models import HeadingCandidate
from .utils import normalize_text, write_json, write_jsonl


TITLE_RE = re.compile(r"<span class=\"title\">(.*?)</span>|<span class='title'>(.*?)</span>", re.IGNORECASE)
PAGETEXT_RE = re.compile(r"<div class='PageText'>(.*?)</div>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
EXERCISE_RE = re.compile(r"أسئلة|تمرين|تطبيق|تدريبات|مسائل", re.IGNORECASE)


def load_must_not(path: Path) -> set[str]:
    blocked: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            text = obj.get("text") or obj.get("snippet") or ""
            if text:
                blocked.add(normalize_text(text))
    return blocked


def _score_heading(text: str) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if len(text) <= 80:
        score += 0.4
        reasons.append("short_line")
    if ARABIC_RE.search(text):
        score += 0.2
        reasons.append("arabic_script")
    if EXERCISE_RE.search(text):
        score += 0.2
        reasons.append("exercise_signal")
    if any(k in text for k in ["باب", "فصل", "مقدمة", "خاتمة", "المجلد"]):
        score += 0.3
        reasons.append("heading_keyword")
    return min(score, 1.0), reasons


def generate_candidates(html_files: list[Path], must_not_path: Path) -> list[HeadingCandidate]:
    blocked = load_must_not(must_not_path)
    candidates: list[HeadingCandidate] = []

    for page_idx, p in enumerate(html_files, start=1):
        raw = p.read_text(encoding="utf-8", errors="replace")
        blocks = PAGETEXT_RE.findall(raw)
        line_i = 0
        for b in blocks:
            for m in TITLE_RE.finditer(b):
                txt = m.group(1) or m.group(2) or ""
                clean = normalize_text(TAG_RE.sub(" ", txt))
                if not clean:
                    continue
                line_i += 1
                score, reasons = _score_heading(clean)
                blocked_reason = "blocked_by_must_not_heading" if clean in blocked else None
                candidates.append(
                    HeadingCandidate(
                        source_file=p.name,
                        page_index=page_idx,
                        line_index=line_i,
                        text=clean,
                        normalized_text=clean,
                        score=score,
                        reasons=reasons,
                        blocked_reason=blocked_reason,
                    )
                )
    return candidates


def write_proposed_artifacts(
    candidates: list[HeadingCandidate],
    run_dir: Path,
    threshold: float = 0.55,
) -> dict:
    proposal_path = run_dir / "heading_injections.proposed.jsonl"
    accepted = [c for c in candidates if c.score >= threshold and c.blocked_reason is None]
    blocked = [c for c in candidates if c.blocked_reason]

    rows = []
    for c in candidates:
        row = c.to_dict()
        row["proposal"] = "inject_heading" if c in accepted else "skip"
        row["review_required"] = True
        rows.append(row)
    write_jsonl(proposal_path, rows)

    summary = {
        "candidate_count": len(candidates),
        "proposed_injection_count": len(accepted),
        "blocked_by_must_not_count": len(blocked),
        "policy": "all injections require human approval",
    }
    write_json(run_dir / "heading_injections.summary.json", summary)
    return summary
