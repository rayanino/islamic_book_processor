import re

from ibp.cli import main


def test_run_id_layout_created(tmp_path):
    result = main([
        "scan",
        "BK001_shadha_al_urf",
        "--fixtures-root",
        "fixtures/shamela_exports",
        "--runs-root",
        str(tmp_path),
    ])
    assert result == 0

    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert re.fullmatch(r"\d{8}T\d{6}Z", run_dir.name)

    book_dir = run_dir / "BK001_shadha_al_urf"
    assert (book_dir / "logs").is_dir()
    assert (book_dir / "artifacts").is_dir()
    assert (book_dir / "artifacts" / "bookcatcher.scan.json").is_file()
