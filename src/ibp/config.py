"""Configuration and path-safety helpers for IBP."""

from __future__ import annotations

import re
from pathlib import Path

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_INVALID_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_path_component(value: str) -> str:
    """Return a cross-platform-safe path component.

    Replaces invalid characters with underscores, trims trailing spaces/dots,
    and avoids Windows reserved names.
    """

    cleaned = _INVALID_COMPONENT_CHARS.sub("_", value).strip().rstrip(". ")
    if not cleaned:
        cleaned = "unnamed"

    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_"

    return cleaned


def resolve_runs_dir(runs_dir: str | Path) -> Path:
    """Normalize the runs directory into a pathlib.Path."""

    return Path(runs_dir)
