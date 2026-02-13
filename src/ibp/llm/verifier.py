from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ibp.llm.cache import LLMPersistentCache

_ALLOWED_REASONS = {"title", "metadata", "footnote", "pagehead", "body_line"}


class LLMValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LLMVerifierDecision:
    is_heading: bool
    level: int
    normalized_title: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class LLMVerifierResult:
    candidate_id: str
    signature: str
    model: str
    prompt_hash: str
    from_cache: bool
    decision: LLMVerifierDecision


def _strict_validate(payload: dict[str, Any]) -> LLMVerifierDecision:
    required = {"is_heading", "level", "normalized_title", "confidence", "reason"}
    keys = set(payload.keys())
    if keys != required:
        extra = sorted(keys - required)
        missing = sorted(required - keys)
        raise LLMValidationError(f"Strict schema mismatch. missing={missing} extra={extra}")

    is_heading = payload["is_heading"]
    level = payload["level"]
    normalized_title = payload["normalized_title"]
    confidence = payload["confidence"]
    reason = payload["reason"]

    if not isinstance(is_heading, bool):
        raise LLMValidationError("is_heading must be bool")
    if level not in (2, 3):
        raise LLMValidationError("level must be 2 or 3")
    if not isinstance(normalized_title, str):
        raise LLMValidationError("normalized_title must be str")
    if not isinstance(confidence, (int, float)):
        raise LLMValidationError("confidence must be number")
    if not (0.0 <= float(confidence) <= 1.0):
        raise LLMValidationError("confidence must be in [0,1]")
    if reason not in _ALLOWED_REASONS:
        raise LLMValidationError("reason not in allowed enum")

    return LLMVerifierDecision(
        is_heading=is_heading,
        level=level,
        normalized_title=normalized_title.strip(),
        confidence=float(confidence),
        reason=reason,
    )


class LLMVerifier:
    def __init__(
        self,
        *,
        run_id: str,
        model: str,
        artifacts_dir: Path,
        provider: Callable[[dict[str, Any]], dict[str, Any]] | None,
        max_retries: int = 3,
        backoff_seconds: float = 0.25,
    ) -> None:
        self.run_id = run_id
        self.model = model
        self.provider = provider
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.cache = LLMPersistentCache(artifacts_dir / "llm_cache.json")
        self.state_path = artifacts_dir / "llm_verifier.state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("run_id") == self.run_id:
                return payload
        return {"run_id": self.run_id, "completed_signatures": []}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _build_prompt(self, candidate: dict[str, Any]) -> str:
        return (
            "Classify candidate as heading/non-heading. Return strict JSON only with keys: "
            "is_heading, level (2|3), normalized_title, confidence (0..1), reason.\n"
            f"text={candidate.get('text', '')}\n"
            f"kind={candidate.get('kind', '')}\n"
            f"context_before={candidate.get('context_before', '')}\n"
            f"context_after={candidate.get('context_after', '')}\n"
        )

    def _invoke_with_retry(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.provider is None:
            raise RuntimeError("LLM provider is unavailable")
        attempt = 0
        last_error: Exception | None = None
        while attempt < self.max_retries:
            try:
                response = self.provider(request)
                if not isinstance(response, dict):
                    raise LLMValidationError("LLM response must be dict")
                _strict_validate(response)
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempt += 1
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(f"LLM verifier failed after retries: {last_error}")

    def verify_candidate(self, candidate: dict[str, Any]) -> LLMVerifierResult:
        prompt = self._build_prompt(candidate)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        signature = str(candidate.get("signature", ""))
        key = self.cache.make_key(candidate_signature=signature, model=self.model, prompt_hash=prompt_hash)

        cached = self.cache.get(key)
        if cached is not None:
            decision = _strict_validate(cached)
            return LLMVerifierResult(
                candidate_id=str(candidate.get("candidate_id", "")),
                signature=signature,
                model=self.model,
                prompt_hash=prompt_hash,
                from_cache=True,
                decision=decision,
            )

        response = self._invoke_with_retry({"model": self.model, "prompt": prompt, "candidate": candidate})
        decision = _strict_validate(response)
        self.cache.put(key, response)

        completed = self._state.get("completed_signatures")
        if isinstance(completed, list) and signature not in completed:
            completed.append(signature)
            self._save_state()

        return LLMVerifierResult(
            candidate_id=str(candidate.get("candidate_id", "")),
            signature=signature,
            model=self.model,
            prompt_hash=prompt_hash,
            from_cache=False,
            decision=decision,
        )


def is_ambiguous(score: float, *, center: float = 0.5, margin: float = 0.15) -> bool:
    return abs(score - center) <= margin
