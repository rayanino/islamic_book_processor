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
    assert (artifacts / "topic_placements.proposed.json").exists()


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


def test_apply_routes_low_confidence_placements_to_review(tmp_path):
    run_dir = tmp_path / "runs" / "R3" / "BK"
    artifacts = run_dir / "artifacts"
    _write(run_dir / "derived" / "book.md", "# Book\n\n## Unmatched Heading\nSparse body\n")
    _write(
        artifacts / "chunk_plan.approved.json",
        json.dumps({"items": [{"heading": "Unmatched Heading", "level": 2}]}),
    )
    _write(
        artifacts / "topic_registry.json",
        json.dumps(
            {
                "topics": [
                    {
                        "topic_id": "topic_alpha",
                        "title": "Completely Different",
                        "exemplars": [{"heading": "Other", "body": "different tokens only"}],
                    }
                ]
            }
        ),
    )

    rc = main(["apply", "--runs-root", str(tmp_path / "runs"), "--run-id", "R3", "--book-id", "BK"])
    assert rc == 0

    review = json.loads((run_dir / "_REVIEW" / "topic_placements.review.json").read_text(encoding="utf-8"))
    assert review["status"] == "review_required"
    assert review["items"][0]["machine_reasons"] == ["confidence_below_threshold"]
    assert review["items"][0]["candidate_alternatives"][0]["topic_id"] == "topic_alpha"

    proposed = json.loads((artifacts / "topic_placements.proposed.json").read_text(encoding="utf-8"))
    assert proposed["items"][0]["review_required"] is True


def test_apply_uses_registry_topic_id_for_high_confidence_placement(tmp_path):
    run_dir = tmp_path / "runs" / "R4" / "BK"
    artifacts = run_dir / "artifacts"
    _write(run_dir / "derived" / "book.md", "# Book\n\n## نحو\nالنحو قواعد نحو\n")
    _write(
        artifacts / "chunk_plan.approved.json",
        json.dumps({"items": [{"heading": "نحو", "level": 2}]}),
    )
    _write(
        artifacts / "topic_registry.json",
        json.dumps(
            {
                "topics": [
                    {
                        "topic_id": "topic_nahw",
                        "title": "نحو",
                        "exemplars": [{"heading": "نحو", "body": "قواعد نحو"}],
                    }
                ]
            }
        ),
    )

    rc = main(["apply", "--runs-root", str(tmp_path / "runs"), "--run-id", "R4", "--book-id", "BK"])
    assert rc == 0

    placements = json.loads((artifacts / "topic_placements.applied.json").read_text(encoding="utf-8"))
    assert placements["items"][0]["status"] == "assigned"
    assert placements["items"][0]["chosen_topic_id"] == "topic_nahw"
    assert not (run_dir / "_REVIEW" / "topic_placements.review.json").exists()
