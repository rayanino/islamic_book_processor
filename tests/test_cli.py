from pathlib import Path
import json

from ibp.cli import main


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
    ]
    monkeypatch.setattr("sys.argv", approve_args)
    rc = main()
    assert rc == 0

    art = run_root / "T1" / "BK001_shadha_al_urf" / "artifacts"
    assert (art / "heading_injections.approved.jsonl").exists()
    assert (art / "chunk_plan.approved.json").exists()
    assert (run_root / "T1" / "BK001_shadha_al_urf" / "run_report.json").exists()
