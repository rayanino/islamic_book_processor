from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from html import unescape
from pathlib import Path

from ibp.ingest.manifest import read_text_encoding_safe

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
AR_HEADING_CUES = ("باب", "فصل", "كتاب", "تنبيه", "مسألة", "مقدمة", "خاتمة")


@dataclass(frozen=True)
class HeadingCandidate:
    candidate_id: str
    file: str
    line_no: int
    text: str
    kind: str
    signature: str
    context_before: str
    context_after: str
    html_excerpt: str


def _strip_html(s: str) -> str:
    return WS_RE.sub(" ", unescape(TAG_RE.sub(" ", s))).strip()


def _kind_for(raw_line: str, text: str) -> str:
    low = raw_line.lower()
    if "footnote" in low or "حاشية" in text:
        return "footnote"
    if "pagehead" in low or "pagenumber" in low:
        return "pagehead"
    if any(t in text for t in ("المؤلف", "الناشر", "الطبعة")):
        return "metadata"
    return "title" if any(c in text for c in AR_HEADING_CUES) else "body"


def extract_layer_a_candidates(path: Path) -> list[HeadingCandidate]:
    html, _ = read_text_encoding_safe(path)
    raw_lines = html.splitlines()
    stripped = [_strip_html(line) for line in raw_lines]
    candidates: list[HeadingCandidate] = []

    for idx, raw in enumerate(raw_lines):
        text = stripped[idx]
        if not text:
            continue
        titleish = (
            'align="center"' in raw.lower()
            or "text-align:center" in raw.lower().replace(" ", "")
            or any(tag in raw.lower() for tag in ("<b", "<strong", "partname", "title"))
            or any(token in text for token in AR_HEADING_CUES)
        )
        if not titleish:
            continue

        signature_seed = f"{path.name}|{idx}|{text[:120]}"
        signature = hashlib.sha256(signature_seed.encode("utf-8")).hexdigest()[:16]
        cid = hashlib.sha256(f"cand|{signature_seed}".encode("utf-8")).hexdigest()[:20]
        candidates.append(
            HeadingCandidate(
                candidate_id=cid,
                file=path.name,
                line_no=idx + 1,
                text=text,
                kind=_kind_for(raw, text),
                signature=signature,
                context_before=stripped[idx - 1] if idx > 0 else "",
                context_after=stripped[idx + 1] if idx + 1 < len(stripped) else "",
                html_excerpt=raw.strip()[:240],
            )
        )
    return candidates


def candidates_jsonable(candidates: list[HeadingCandidate]) -> list[dict]:
    return [asdict(c) for c in candidates]
