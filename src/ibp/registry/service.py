"""Registry persistence services for topics, lineage, placements, and projections."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ibp.config import sanitize_path_component
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
        self._ensure_topic_allocator_seed()

    def close(self) -> None:
        self.conn.close()

    def _ensure_topic_allocator_seed(self) -> None:
        row = self.conn.execute(
            "SELECT next_numeric_id FROM topic_id_allocator WHERE allocator_key = 'topic'"
        ).fetchone()
        if row is not None:
            return

        max_existing = self.conn.execute(
            """
            SELECT topic_id FROM topics
            WHERE topic_id GLOB 'T[0-9][0-9][0-9][0-9][0-9][0-9]'
            ORDER BY topic_id DESC
            LIMIT 1
            """
        ).fetchone()
        next_id = 1
        if max_existing is not None:
            next_id = int(str(max_existing[0])[1:]) + 1
        self.conn.execute(
            "INSERT INTO topic_id_allocator(allocator_key, next_numeric_id) VALUES('topic', ?)",
            (next_id,),
        )
        self.conn.commit()

    def _bump_topic_allocator_floor(self, topic_id: str) -> None:
        if not re.fullmatch(r"T\d{6}", topic_id):
            return
        numeric_id = int(topic_id[1:])
        row = self.conn.execute(
            "SELECT next_numeric_id FROM topic_id_allocator WHERE allocator_key = 'topic'"
        ).fetchone()
        if row is None:
            self._ensure_topic_allocator_seed()
            row = self.conn.execute(
                "SELECT next_numeric_id FROM topic_id_allocator WHERE allocator_key = 'topic'"
            ).fetchone()
        next_numeric_id = int(row[0])
        if numeric_id >= next_numeric_id:
            self.conn.execute(
                "UPDATE topic_id_allocator SET next_numeric_id = ? WHERE allocator_key = 'topic'",
                (numeric_id + 1,),
            )

    def _allocate_topic_id(self) -> str:
        row = self.conn.execute(
            "SELECT next_numeric_id FROM topic_id_allocator WHERE allocator_key = 'topic'"
        ).fetchone()
        if row is None:
            self._ensure_topic_allocator_seed()
            row = self.conn.execute(
                "SELECT next_numeric_id FROM topic_id_allocator WHERE allocator_key = 'topic'"
            ).fetchone()
        numeric_id = int(row[0])
        self.conn.execute(
            "UPDATE topic_id_allocator SET next_numeric_id = ? WHERE allocator_key = 'topic'",
            (numeric_id + 1,),
        )
        return f"T{numeric_id:06d}"

    @staticmethod
    def _topic_folder_name(topic_id: str, display_title_ar: str) -> str:
        safe_title = sanitize_path_component(display_title_ar or topic_id)
        return f"{topic_id}__{safe_title}"

    def sync_topics(self, topics: list[dict], created_by: str = "topic_registry_import") -> list[dict]:
        now = _utc_now()
        synced_topics: list[dict] = []
        for topic in topics:
            topic_id = (topic.get("topic_id") or "").strip()
            if not topic_id:
                topic_id = self._allocate_topic_id()
            elif re.fullmatch(r"T\d{6}", topic_id):
                self._bump_topic_allocator_floor(topic_id)
            else:
                topic_id = sanitize_path_component(topic_id)
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
            synced_topic = dict(topic)
            synced_topic["topic_id"] = topic_id
            synced_topic["display_title_ar"] = display_title
            synced_topic["aliases"] = aliases
            synced_topic["status"] = status
            synced_topic["parent_topic_id"] = parent_topic_id
            synced_topic["topic_folder_name"] = self._topic_folder_name(topic_id=topic_id, display_title_ar=display_title)
            synced_topics.append(synced_topic)
        self.conn.commit()
        self.export_topics()
        return synced_topics

    def export_topics(self, topic_ids: list[str] | None = None) -> list[dict]:
        where = ""
        params: tuple[str, ...] = ()
        if topic_ids:
            placeholders = ",".join("?" for _ in topic_ids)
            where = f"WHERE topic_id IN ({placeholders})"
            params = tuple(topic_ids)

        rows = self.conn.execute(
            f"""
            SELECT topic_id, parent_topic_id, display_title_ar, aliases_json, status,
                   created_by, created_at, updated_at
            FROM topics
            {where}
            ORDER BY topic_id
            """,
            params,
        ).fetchall()

        topics: list[dict] = []
        for row in rows:
            aliases = json.loads(row["aliases_json"] or "[]")
            topics.append(
                {
                    "topic_id": row["topic_id"],
                    "parent_topic_id": row["parent_topic_id"],
                    "display_title_ar": row["display_title_ar"],
                    "aliases": aliases,
                    "status": row["status"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "topic_folder_name": self._topic_folder_name(
                        topic_id=row["topic_id"],
                        display_title_ar=row["display_title_ar"],
                    ),
                }
            )

        payload = {"topics": topics}
        (self.paths.registry_dir / "topics.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return topics

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
