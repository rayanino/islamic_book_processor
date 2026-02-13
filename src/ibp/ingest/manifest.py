from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

PREFERRED_ENCODINGS = ("utf-8-sig", "utf-8", "cp1256", "latin-1")


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    sha256: str
    encoding: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text_encoding_safe(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for enc in PREFERRED_ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def sorted_source_files(source_raw_dir: Path) -> list[Path]:
    return sorted(
        [p for p in source_raw_dir.iterdir() if p.is_file() and p.suffix.lower() in {".htm", ".html"}],
        key=lambda p: p.name,
    )


def build_book_manifest(source_raw_dir: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for path in sorted_source_files(source_raw_dir):
        _, encoding = read_text_encoding_safe(path)
        records.append(
            FileRecord(
                path=path.name,
                size=path.stat().st_size,
                sha256=sha256_file(path),
                encoding=encoding,
            )
        )
    return records


def manifest_as_jsonable(records: Iterable[FileRecord]) -> list[dict]:
    return [asdict(r) for r in records]
