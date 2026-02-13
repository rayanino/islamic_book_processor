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
    art = run_root / "T1" / "BK001_shadha_al_urf" / "artifacts"
    assert (art / "manifest.json").exists()
    assert (art / "heading_injections.proposed.jsonl").exists()
    assert (art / "chunk_plan.proposed.json").exists()


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
