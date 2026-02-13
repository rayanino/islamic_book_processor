from __future__ import annotations

import re
from pathlib import Path

from .models import BookInput
from .utils import sha256_bytes, write_json


def resolve_book(fixtures_root: Path, book_id: str) -> BookInput:
    book_dir = fixtures_root / book_id
    if not book_dir.exists():
        raise FileNotFoundError(f"Book directory not found: {book_dir}")
    return BookInput(book_id=book_id, book_dir=book_dir)


def collect_html_files(book: BookInput) -> list[Path]:
    raw = book.book_dir / "source_raw"
    files = sorted(raw.glob("*.htm"))
    if not files:
        raise FileNotFoundError(f"No .htm files under {raw}")
    return files


def build_manifest(book: BookInput, html_files: list[Path], out_path: Path) -> dict:
    items = []
    for p in html_files:
        b = p.read_bytes()
        items.append({"file": p.name, "sha256": sha256_bytes(b), "bytes": len(b)})

    payload = {
        "book_id": book.book_id,
        "source_dir": str(book.book_dir),
        "file_count": len(items),
        "files": items,
    }
    write_json(out_path, payload)
    return payload


def book_catcher_scan(html_files: list[Path], out_path: Path) -> dict:
    page_marker_re = re.compile(r"\(ص:\s*[^)]+\)")
    part_name_re = re.compile(r"<span class='PartName'>(.*?)</span>", re.IGNORECASE)
    footnote_re = re.compile(r"class='footnote'|class=\"footnote\"", re.IGNORECASE)
    toc_hint_re = re.compile(r"فهرس|المحتويات", re.IGNORECASE)

    part_names: dict[str, int] = {}
    page_markers = 0
    footnotes = 0
    toc_hints = 0

    for p in html_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        page_markers += len(page_marker_re.findall(text))
        footnotes += len(footnote_re.findall(text))
        toc_hints += len(toc_hint_re.findall(text))
        for part in part_name_re.findall(text):
            part = re.sub(r"\s+", " ", part).strip()
            if part:
                part_names[part] = part_names.get(part, 0) + 1

    repeated_headers = [
        {"text": txt, "count": cnt}
        for txt, cnt in sorted(part_names.items(), key=lambda kv: kv[1], reverse=True)
        if cnt >= 2
    ]

    payload = {
        "page_marker_count": page_markers,
        "footnote_zone_hits": footnotes,
        "toc_hint_count": toc_hints,
        "repeated_running_headers": repeated_headers,
    }
    write_json(out_path, payload)
    return payload
