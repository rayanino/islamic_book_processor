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
