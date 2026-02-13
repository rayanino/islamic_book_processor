from pathlib import Path

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
    run_dir = run_root / "T1" / "BK001_shadha_al_urf"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "heading_injections.proposed.jsonl").exists()
    assert (run_dir / "chunk_plan.proposed.json").exists()


def test_approve_outputs_file(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    run_dir = run_root / "T1" / "BK001_shadha_al_urf"
    run_dir.mkdir(parents=True)
    (run_dir / "heading_injections.proposed.jsonl").write_text('{"proposal":"inject_heading"}\n', encoding="utf-8")
    args = [
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
    monkeypatch.setattr("sys.argv", args)
    rc = main()
    assert rc == 0
    assert (run_dir / "heading_injections.approved.jsonl").exists()
