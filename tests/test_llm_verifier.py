import json

from ibp.llm.verifier import LLMVerifier, is_ambiguous


def test_is_ambiguous_band():
    assert is_ambiguous(0.5)
    assert is_ambiguous(0.64)
    assert not is_ambiguous(0.2)


def test_verifier_uses_cache_and_persists_state(tmp_path):
    artifacts = tmp_path / "artifacts"
    calls = {"n": 0}

    def provider(_request: dict) -> dict:
        calls["n"] += 1
        return {
            "is_heading": True,
            "level": 2,
            "normalized_title": "باب",
            "confidence": 0.9,
            "reason": "title",
        }

    candidate = {
        "candidate_id": "c1",
        "signature": "s1",
        "text": "باب",
        "kind": "title",
        "context_before": "",
        "context_after": "",
    }

    verifier = LLMVerifier(run_id="R1", model="m1", artifacts_dir=artifacts, provider=provider)
    first = verifier.verify_candidate(candidate)
    second = verifier.verify_candidate(candidate)

    assert calls["n"] == 1
    assert not first.from_cache
    assert second.from_cache

    state = json.loads((artifacts / "llm_verifier.state.json").read_text(encoding="utf-8"))
    assert state["run_id"] == "R1"
    assert "s1" in state["completed_signatures"]


def test_verifier_retries_on_schema_failure(tmp_path):
    artifacts = tmp_path / "artifacts"
    calls = {"n": 0}

    def provider(_request: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"bad": True}
        return {
            "is_heading": False,
            "level": 2,
            "normalized_title": "",
            "confidence": 0.2,
            "reason": "body_line",
        }

    verifier = LLMVerifier(
        run_id="R1",
        model="m1",
        artifacts_dir=artifacts,
        provider=provider,
        backoff_seconds=0.0,
    )
    res = verifier.verify_candidate(
        {
            "candidate_id": "c1",
            "signature": "s2",
            "text": "foo",
            "kind": "body",
            "context_before": "",
            "context_after": "",
        }
    )
    assert res.decision.reason == "body_line"
    assert calls["n"] == 2
