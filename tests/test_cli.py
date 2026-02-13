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


def test_apply_writes_canonical_and_registry(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    corpus_root = tmp_path / "corpus"

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
        ],
    )
    assert main() == 0

    monkeypatch.setattr(
        "sys.argv",
        [
            "ibp",
            "apply",
            "--runs-root",
            str(run_root),
            "--fixtures-root",
            "fixtures/shamela_exports",
            "--run-id",
            "T2",
            "--book-id",
            "BK001_shadha_al_urf",
            "--corpus-root",
            str(corpus_root),
            "--science",
            "Sarf",
        ],
    )
    assert main() == 0

    canonical = corpus_root / "Sarf" / "chunks_by_book" / "BK001_shadha_al_urf"
    registry = corpus_root / "Sarf" / "registry" / "topics.sqlite"
    assert canonical.exists()
    assert any(canonical.glob("chunk_*.md"))
    assert registry.exists()
