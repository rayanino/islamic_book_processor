"""Registry persistence services for topics, lineage, placements, and projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ibp.registry.migrations import ensure_migrations


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RegistryPaths:
    artifacts_dir: Path

    @property
    def registry_dir(self) -> Path:
        return self.artifacts_dir / "registry"

    @property
    def db_path(self) -> Path:
        return self.registry_dir / "registry.sqlite3"


class RegistryService:
    """Small service layer so CLI never performs inline SQL."""

    def __init__(self, artifacts_dir: Path, run_id: str) -> None:
        self.paths = RegistryPaths(artifacts_dir=artifacts_dir)
        self.run_id = run_id
        self.paths.registry_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.paths.db_path)
        self.conn.row_factory = sqlite3.Row
        ensure_migrations(self.conn)

    def close(self) -> None:
        self.conn.close()

    def sync_topics(self, topics: list[dict], created_by: str = "topic_registry_import") -> None:
        now = _utc_now()
        for topic in topics:
            topic_id = (topic.get("topic_id") or "").strip()
            if not topic_id:
                continue
            display_title = (
                topic.get("display_title_ar")
                or topic.get("title")
                or topic.get("heading")
                or topic_id
            )
            aliases = topic.get("aliases")
            if not isinstance(aliases, list):
                aliases = []
            status = topic.get("status") or "active"
            parent_topic_id = topic.get("parent_topic_id")
            self.conn.execute(
                """
                INSERT INTO topics(
                    topic_id, parent_topic_id, display_title_ar, aliases_json, status,
                    created_by, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    parent_topic_id=excluded.parent_topic_id,
                    display_title_ar=excluded.display_title_ar,
                    aliases_json=excluded.aliases_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    topic_id,
                    parent_topic_id,
                    display_title,
                    json.dumps(aliases, ensure_ascii=False),
                    status,
                    created_by,
                    now,
                    now,
                ),
            )
        self.conn.commit()

    def add_chunk_version(self, chunk_key: str, approved_item: dict, chunk_features: dict) -> int:
        now = _utc_now()
        row = self.conn.execute(
            """
            SELECT chunk_version_id FROM chunk_versions
            WHERE chunk_key = ?
            ORDER BY chunk_version_id DESC
            LIMIT 1
            """,
            (chunk_key,),
        ).fetchone()
        supersedes_id = int(row[0]) if row else None
        cur = self.conn.execute(
            """
            INSERT INTO chunk_versions(
                chunk_key, run_id, source_kind, source_ref, heading, body_excerpt,
                canonical_payload_json, supersedes_chunk_version_id, deprecation_reason, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_key,
                self.run_id,
                "chunk_plan.approved",
                "artifacts/chunk_plan.approved.json#items",
                chunk_features.get("heading"),
                chunk_features.get("body_excerpt"),
                json.dumps(approved_item, ensure_ascii=False),
                supersedes_id,
                "canonical_replacement" if supersedes_id else None,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_placement_decision(self, chunk_version_id: int, placement_payload: dict) -> None:
        confidence = float(placement_payload.get("confidence") or 0.0)
        reviewer_action = "needs_review" if placement_payload.get("status") == "review" else "auto_assigned"
        rationale = {
            "reasons": placement_payload.get("reasons", []),
            "candidate_alternatives": placement_payload.get("candidate_alternatives", []),
        }
        self.conn.execute(
            """
            INSERT INTO placement_decisions(
                run_id, chunk_version_id, chosen_topic_id, status, rationale_json,
                confidence, reviewer_action, reviewer_id, decided_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                chunk_version_id,
                placement_payload.get("chosen_topic_id"),
                placement_payload.get("status") or "review",
                json.dumps(rationale, ensure_ascii=False),
                confidence,
                reviewer_action,
                "system_apply",
                _utc_now(),
            ),
        )
        self.conn.commit()

    def add_projection(self, projection_kind: str, source_ref: str, payload: dict) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        source_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        deterministic_key = f"{projection_kind}:{source_hash}"
        self.conn.execute(
            """
            INSERT INTO projections(
                run_id, projection_kind, source_ref, source_hash, deterministic_key,
                generator_version, generated_at, payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, projection_kind, deterministic_key) DO UPDATE SET
                generated_at=excluded.generated_at,
                payload_json=excluded.payload_json
            """,
            (
                self.run_id,
                projection_kind,
                source_ref,
                source_hash,
                deterministic_key,
                "ibp.apply.v1",
                _utc_now(),
                payload_json,
            ),
        )
        self.conn.commit()
