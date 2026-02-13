from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LLMPersistentCache:
    """Persistent cache keyed by candidate signature + model + prompt hash."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            self._data = {}
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            self._data = {}
            return
        self._data = {
            str(k): v for k, v in payload.items() if isinstance(v, dict)
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def make_key(*, candidate_signature: str, model: str, prompt_hash: str) -> str:
        return f"{candidate_signature}|{model}|{prompt_hash}"

    def get(self, key: str) -> dict[str, Any] | None:
        self._load()
        value = self._data.get(key)
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        self._load()
        self._data[key] = value
        self._save()
