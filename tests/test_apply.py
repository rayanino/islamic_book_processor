import json
from pathlib import Path

from ibp.cli import main


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_apply_uses_approved_items_and_writes_applied_artifact(tmp_path):
    run_dir = tmp_path / "runs" / "R1" / "BK"
    artifacts = run_dir / "artifacts"
    _write(
        run_dir / "derived" / "book.md",
        "# Book\n\n## Intro\ntext\n\n### Detail\nmore\n",
    )
    _write(
        artifacts / "chunk_plan.approved.json",
        json.dumps(
            {
                "items": [
                    {"heading": "Intro", "level": 2},
                    {"heading": "Detail", "level": 3},
                ]
            }
        ),
    )

    rc = main(["apply", "--runs-root", str(tmp_path / "runs"), "--run-id", "R1", "--book-id", "BK"])
    assert rc == 0
    payload = json.loads((artifacts / "chunking.applied.json").read_text(encoding="utf-8"))
    assert payload["boundaries_source"] == "artifacts/chunk_plan.approved.json#items"
    assert [item["heading"] for item in payload["applied_items"]] == ["Intro", "Detail"]


def test_apply_fails_closed_and_writes_mismatch_artifact(tmp_path):
    run_dir = tmp_path / "runs" / "R2" / "BK"
    artifacts = run_dir / "artifacts"
    _write(run_dir / "derived" / "book.md", "# Book\n\n## Intro\n")
    _write(
        artifacts / "chunk_plan.approved.json",
        json.dumps({"items": [{"heading": "Missing", "level": 2}]}),
    )

    rc = main(["apply", "--runs-root", str(tmp_path / "runs"), "--run-id", "R2", "--book-id", "BK"])
    assert rc == 1
    mismatch = json.loads((artifacts / "apply.boundary_mismatch.json").read_text(encoding="utf-8"))
    assert mismatch["status"] == "failed_closed"
    assert mismatch["mismatches"][0]["approved_item"]["heading"] == "Missing"
