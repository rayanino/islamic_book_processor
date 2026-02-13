import json

from ibp.registry.service import RegistryService


def test_sync_topics_allocates_monotonic_topic_ids_and_folder_names(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    service = RegistryService(artifacts_dir=artifacts_dir, run_id="R1")
    try:
        synced = service.sync_topics(
            [
                {"display_title_ar": "النحو/الأساسي", "aliases": ["نحو"]},
                {"display_title_ar": "الصرف", "aliases": ["تصريف"]},
            ]
        )
    finally:
        service.close()

    assert [topic["topic_id"] for topic in synced] == ["T000001", "T000002"]
    assert synced[0]["display_title_ar"] == "النحو/الأساسي"
    assert synced[0]["aliases"] == ["نحو"]
    assert synced[0]["topic_folder_name"] == "T000001__النحو_الأساسي"

    exported = json.loads((artifacts_dir / "registry" / "topics.json").read_text(encoding="utf-8"))
    assert exported["topics"][0]["topic_folder_name"].startswith("T000001__")


def test_sync_topics_keeps_existing_topic_id_and_allocates_after_max(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    service = RegistryService(artifacts_dir=artifacts_dir, run_id="R1")
    try:
        service.sync_topics([{"topic_id": "T000123", "display_title_ar": "بلاغة"}])
        synced = service.sync_topics([{"display_title_ar": "أصول"}])
    finally:
        service.close()

    assert synced[0]["topic_id"] == "T000124"
    assert synced[0]["topic_folder_name"] == "T000124__أصول"


def test_registry_tracks_notes_lineage_provenance_and_projection_regeneration(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    service = RegistryService(artifacts_dir=artifacts_dir, run_id="R2")
    try:
        service.sync_topics([{"topic_id": "topic1", "display_title_ar": "فقه", "notes": "seed note"}])

        chunk_features = {"heading": "فقه", "body_excerpt": "body"}
        placement_payload = {
            "status": "assigned",
            "confidence": 0.9,
            "chosen_topic_id": "topic1",
            "reasons": ["high_similarity"],
            "candidate_alternatives": [],
        }
        service.record_chunk_placement(
            chunk_key="BK:1:10:فقه",
            approved_item={"heading": "فقه", "level": 2},
            chunk_features=chunk_features,
            placement_payload=placement_payload,
            reviewer_id="reviewer_a",
        )
        service.add_projection("chunking.applied", "ref", {"value": 1})
        service.add_projection("chunking.applied", "ref", {"value": 2})
    finally:
        service.close()

    service = RegistryService(artifacts_dir=artifacts_dir, run_id="R3")
    try:
        service.record_chunk_placement(
            chunk_key="BK:1:10:فقه",
            approved_item={"heading": "فقه", "level": 2, "revision": 2},
            chunk_features=chunk_features,
            placement_payload=placement_payload,
            reviewer_id="reviewer_b",
        )
    finally:
        service.close()

    import sqlite3

    conn = sqlite3.connect(artifacts_dir / "registry" / "registry.sqlite3")
    try:
        note = conn.execute("SELECT notes FROM topic_notes WHERE topic_id = 'topic1'").fetchone()
        assert note[0] == "seed note"

        lineage_count = conn.execute("SELECT COUNT(*) FROM chunk_lineage_links").fetchone()[0]
        provenance_count = conn.execute("SELECT COUNT(*) FROM placement_decision_provenance").fetchone()[0]
        regen_count = conn.execute("SELECT COUNT(*) FROM projection_regenerations").fetchone()[0]

        assert lineage_count == 1
        assert provenance_count == 2
        assert regen_count == 1
    finally:
        conn.close()
