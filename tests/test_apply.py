import sqlite3
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
    proposal_metrics = json.loads((artifacts / "proposal.metrics.json").read_text(encoding="utf-8"))
    assert proposal_metrics["measurement_method"]["approved_path"].endswith("derived/book.md")


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
    validation = json.loads((artifacts / "apply.validation_errors.json").read_text(encoding="utf-8"))
    assert mismatch["status"] == "failed_closed"
    assert validation["status"] == "failed_closed"
    assert validation["errors"][0]["approved_item"]["heading"] == "Missing"
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


def test_apply_persists_registry_entities_in_sqlite(tmp_path):
    run_dir = tmp_path / "runs" / "R5" / "BK"
    artifacts = run_dir / "artifacts"
    _write(run_dir / "derived" / "book.md", "# Book\n\n## فقه\nتفاصيل فقه\n")
    _write(
        artifacts / "chunk_plan.approved.json",
        json.dumps({"items": [{"heading": "فقه", "level": 2, "line_number": 3}]}),
    )
    _write(
        artifacts / "topic_registry.json",
        json.dumps(
            {
                "topics": [
                    {
                        "topic_id": "topic_fiqh",
                        "display_title_ar": "فقه",
                        "aliases": ["أحكام"],
                        "status": "active",
                        "created_by": "seed",
                    }
                ]
            }
        ),
    )

    rc = main(["apply", "--runs-root", str(tmp_path / "runs"), "--run-id", "R5", "--book-id", "BK"])
    assert rc == 0

    db_path = artifacts / "registry" / "registry.sqlite3"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        topic = conn.execute("SELECT topic_id, display_title_ar FROM topics").fetchone()
        assert topic == ("topic_fiqh", "فقه")

        chunk_count = conn.execute("SELECT COUNT(*) FROM chunk_versions").fetchone()[0]
        placement_count = conn.execute("SELECT COUNT(*) FROM placement_decisions").fetchone()[0]
        projection_count = conn.execute("SELECT COUNT(*) FROM projections").fetchone()[0]
        assert chunk_count == 1
        assert placement_count == 1
        assert projection_count == 1
    finally:
        conn.close()


def test_apply_guardrail_violation_writes_terminal_failure_state(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "R6" / "BK"
    artifacts = run_dir / "artifacts"
    _write(run_dir / "derived" / "book.md", "# Book\n\n## Intro\ntext\n")
    _write(artifacts / "chunk_plan.approved.json", json.dumps({"items": [{"heading": "Intro", "level": 2}]}))

    from ibp.qa import GuardrailViolationError

    def _raise_guardrail(**kwargs):
        report_path = run_dir / "run_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"guardrail_violations": ["anchor_miss_after must be lower than anchor_miss_before"]}),
            encoding="utf-8",
        )
        raise GuardrailViolationError("Mandatory guardrails violated")

    monkeypatch.setattr("ibp.cli.write_run_report", _raise_guardrail)
    rc = main(["apply", "--runs-root", str(tmp_path / "runs"), "--run-id", "R6", "--book-id", "BK", "--mode", "development"])
    assert rc == 1

    run_state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    run_report = json.loads((run_dir / "run_report.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "QA_FAILED"
    assert "anchor_miss_after must be lower than anchor_miss_before" in run_state["failure_reasons"]
    assert run_report["status"] == "qa_failed"
