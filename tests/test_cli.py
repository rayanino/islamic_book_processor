from pathlib import Path
import json

from ibp.cli import main
from ibp.qa import GuardrailViolationError


def test_propose_creates_artifacts(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    args = [
        "ibp",
        "propose",
        "--book-id",
        "BK001_shadha_al_urf",
        "--fixtures-root",
        "fixtures/shamela_exports",
        "--runs-root",
        str(run_root),
        "--run-id",
        "T1",
    ]
    monkeypatch.setattr("sys.argv", args)
    rc = main()
    assert rc == 0
    art = run_root / "T1" / "BK001_shadha_al_urf" / "artifacts"
    assert (art / "manifest.json").exists()
    assert (art / "heading_injections.proposed.jsonl").exists()
    assert (art / "chunk_plan.proposed.json").exists()
    assert (art / "heading_llm_verifier.debug.json").exists()

    first_row = json.loads((art / "heading_injections.proposed.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first_row["review_required"] is True
    assert "suggestion_source" in first_row


def test_approve_outputs_files(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    args = [
        "ibp",
        "propose",
        "--book-id",
        "BK001_shadha_al_urf",
        "--fixtures-root",
        "fixtures/shamela_exports",
        "--runs-root",
        str(run_root),
        "--run-id",
        "T1",
    ]
    monkeypatch.setattr("sys.argv", args)
    assert main() == 0

    derived = run_root / "T1" / "BK001_shadha_al_urf" / "derived" / "book.md"
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text("# Book\n\n## Intro\ntext\n", encoding="utf-8")

    captured = {}

    def _write_ok_report(**kwargs):
        captured.update(kwargs)
        report_path = run_root / "T1" / "BK001_shadha_al_urf" / "run_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"guardrail_violations": [], "status": "passed"}),
            encoding="utf-8",
        )
        return report_path, report_path.with_suffix(".md"), {"guardrail_violations": []}

    monkeypatch.setattr("ibp.cli.write_run_report", _write_ok_report)

    approve_args = [
        "ibp",
        "approve",
        "--runs-root",
        str(run_root),
        "--run-id",
        "T1",
        "--book-id",
        "BK001_shadha_al_urf",
        "--approve-all",
        "--mode",
        "development",
    ]
    monkeypatch.setattr("sys.argv", approve_args)
    rc = main()
    assert rc == 0

    art = run_root / "T1" / "BK001_shadha_al_urf" / "artifacts"
    assert (art / "heading_injections.approved.jsonl").exists()
    assert (art / "chunk_plan.approved.json").exists()
    assert (run_root / "T1" / "BK001_shadha_al_urf" / "run_report.json").exists()
    metrics = json.loads((art / "proposal.metrics.json").read_text(encoding="utf-8"))
    assert metrics["anchor_miss_before"] == captured["anchor_miss_before"]
    assert metrics["anchor_miss_after"] == captured["anchor_miss_after"]
    assert captured["anchor_measurement_metadata"]["strategy"] == "derived_markdown_pair"


def test_approve_guardrail_violation_writes_terminal_failure_state(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    monkeypatch.setattr(
        "sys.argv",
        [
            "ibp",
            "propose",
            "--book-id",
            "BK001_shadha_al_urf",
            "--fixtures-root",
            "fixtures/shamela_exports",
            "--runs-root",
            str(run_root),
            "--run-id",
            "T2",
        ],
    )
    assert main() == 0

    derived = run_root / "T2" / "BK001_shadha_al_urf" / "derived" / "book.md"
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text("# Book\n\n## Intro\ntext\n", encoding="utf-8")

    def _raise_guardrail(**kwargs):
        report_path = run_root / "T2" / "BK001_shadha_al_urf" / "run_report.json"
        report_path.write_text(
            json.dumps({"guardrail_violations": ["anchor_miss_after must be lower than anchor_miss_before"]}),
            encoding="utf-8",
        )
        raise GuardrailViolationError("Mandatory guardrails violated")

    monkeypatch.setattr("ibp.cli.write_run_report", _raise_guardrail)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ibp",
            "approve",
            "--runs-root",
            str(run_root),
            "--run-id",
            "T2",
            "--book-id",
            "BK001_shadha_al_urf",
            "--approve-all",
            "--mode",
            "development",
        ],
    )
    assert main() == 1

    run_dir = run_root / "T2" / "BK001_shadha_al_urf"
    run_state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    run_report = json.loads((run_dir / "run_report.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "QA_FAILED"
    assert "anchor_miss_after must be lower than anchor_miss_before" in run_state["failure_reasons"]
    assert run_report["status"] == "qa_failed"
