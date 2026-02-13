from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, asdict
from html import unescape
from pathlib import Path

from ibp.ingest.manifest import read_text_encoding_safe

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
TOC_TOKENS = ("فهرس", "المحتويات", "جدول المحتويات", "باب")
META_TOKENS = ("المؤلف", "تحقيق", "الناشر", "الطبعة", "حقوق")


@dataclass(frozen=True)
class ScanSignals:
    page_markers: list[str]
    repeated_headers: list[str]
    repeated_footers: list[str]
    footnote_markers: int
    metadata_zone_hits: int
    embedded_toc_hints: list[str]


def _to_text(html: str) -> str:
    text = TAG_RE.sub(" ", html)
    text = unescape(text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _candidate_lines(html: str) -> list[str]:
    lines = []
    for raw in html.splitlines():
        text = _to_text(raw)
        if text:
            lines.append(text)
    return lines


def scan_book_html(files: list[Path]) -> ScanSignals:
    all_first: list[str] = []
    all_last: list[str] = []
    page_markers: list[str] = []
    footnote_markers = 0
    metadata_zone_hits = 0
    toc_hints: list[str] = []

    for ix, path in enumerate(files):
        html, _ = read_text_encoding_safe(path)
        lines = _candidate_lines(html)
        if lines:
            all_first.append(lines[0])
            all_last.append(lines[-1])

        page_markers.extend(re.findall(r"(?:صفحة|Page)\s*[:\-]?\s*\d+", html, flags=re.IGNORECASE))
        footnote_markers += len(re.findall(r"footnote|حاشية|\[\d+\]", html, flags=re.IGNORECASE))

        if ix < 2:
            metadata_zone_hits += sum(1 for token in META_TOKENS if token in html)
        if any(token in html for token in TOC_TOKENS):
            toc_hints.append(path.name)

    first_counts = Counter(all_first)
    last_counts = Counter(all_last)
    repeated_headers = [t for t, c in first_counts.items() if c > 1]
    repeated_footers = [t for t, c in last_counts.items() if c > 1]

    return ScanSignals(
        page_markers=sorted(set(page_markers)),
        repeated_headers=repeated_headers,
        repeated_footers=repeated_footers,
        footnote_markers=footnote_markers,
        metadata_zone_hits=metadata_zone_hits,
        embedded_toc_hints=sorted(set(toc_hints)),
    )


def scan_signals_jsonable(signals: ScanSignals) -> dict:
    return asdict(signals)
