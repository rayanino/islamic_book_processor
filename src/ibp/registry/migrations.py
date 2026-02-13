"""SQLite migrations for registry persistence."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="create_topics",
        sql="""
        CREATE TABLE IF NOT EXISTS topics (
            topic_id TEXT PRIMARY KEY,
            parent_topic_id TEXT,
            display_title_ar TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_topics_parent_topic_id ON topics(parent_topic_id);
        """,
    ),
    Migration(
        version=2,
        name="create_chunk_versions",
        sql="""
        CREATE TABLE IF NOT EXISTS chunk_versions (
            chunk_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            heading TEXT,
            body_excerpt TEXT,
            canonical_payload_json TEXT NOT NULL,
            supersedes_chunk_version_id INTEGER,
            deprecation_reason TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(chunk_key, run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_versions_chunk_key ON chunk_versions(chunk_key);
        """,
    ),
    Migration(
        version=3,
        name="create_placement_decisions",
        sql="""
        CREATE TABLE IF NOT EXISTS placement_decisions (
            placement_decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            chunk_version_id INTEGER NOT NULL,
            chosen_topic_id TEXT,
            status TEXT NOT NULL,
            rationale_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            reviewer_action TEXT,
            reviewer_id TEXT,
            decided_at TEXT NOT NULL,
            FOREIGN KEY(chunk_version_id) REFERENCES chunk_versions(chunk_version_id),
            FOREIGN KEY(chosen_topic_id) REFERENCES topics(topic_id)
        );
        CREATE INDEX IF NOT EXISTS idx_placement_decisions_run_id ON placement_decisions(run_id);
        """,
    ),
    Migration(
        version=4,
        name="create_projections",
        sql="""
        CREATE TABLE IF NOT EXISTS projections (
            projection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            projection_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            deterministic_key TEXT NOT NULL,
            generator_version TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(run_id, projection_kind, deterministic_key)
        );
        CREATE INDEX IF NOT EXISTS idx_projections_run_kind ON projections(run_id, projection_kind);
        """,
    ),
)


def ensure_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations to the registry database."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """
    )

    applied = {
        row[0]
        for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    }

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        conn.executescript(migration.sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, name) VALUES(?, ?)",
            (migration.version, migration.name),
        )
    conn.commit()
