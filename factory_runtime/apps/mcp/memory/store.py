"""MemoryStore — SQLite backend for the mcp-memory server.

Three tables:
- lessons: per-issue learnings (issue_number, outcome, learnings_json, ts)
- entities: knowledge graph nodes (name, kind, metadata_json)
- relationships: knowledge graph edges (from_entity, relation, to_entity)

All writes are idempotent. All reads return empty lists/dicts rather than None.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from factory_runtime.apps.mcp.sqlite_permissions import (
    finalize_sqlite_path,
    prepare_sqlite_path,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_project_id(project_id: str) -> str:
    normalized = str(project_id).strip()
    if not normalized:
        raise ValueError("project_id must be a non-empty string")
    return normalized


class MemoryStore:
    """SQLite-backed memory store for FACTORY agent memory layers."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        if self._db_path != ":memory:":
            self._db_path = str(prepare_sqlite_path(self._db_path))
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.row_factory = sqlite3.Row
        self._migrate()
        if self._db_path != ":memory:":
            finalize_sqlite_path(self._db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                project_id      TEXT NOT NULL DEFAULT 'default',
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_number INTEGER NOT NULL,
                repo        TEXT NOT NULL DEFAULT '',
                outcome     TEXT NOT NULL,           -- 'success' | 'failure' | 'partial'
                summary     TEXT NOT NULL,
                learnings   TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
                ts          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entities (
                project_id      TEXT NOT NULL DEFAULT 'default',
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                kind        TEXT NOT NULL,           -- 'file' | 'domain' | 'service' | 'issue'
                metadata    TEXT NOT NULL DEFAULT '{}',
                ts          TEXT NOT NULL,
                UNIQUE(project_id, name, kind)
            );

            CREATE TABLE IF NOT EXISTS relationships (
                project_id      TEXT NOT NULL DEFAULT 'default',
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                from_entity TEXT NOT NULL,
                relation    TEXT NOT NULL,           -- 'belongs_to' | 'changed_by' | 'depends_on'
                to_entity   TEXT NOT NULL,
                ts          TEXT NOT NULL,
                UNIQUE(project_id, from_entity, relation, to_entity)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                project_id      TEXT NOT NULL DEFAULT 'default',
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT NOT NULL,
                details     TEXT NOT NULL DEFAULT '{}',
                ts          TEXT NOT NULL
            );
            """
        )
        self._ensure_relationship_partitioning()
        self._conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_lessons_project_issue_ts
            ON lessons(project_id, issue_number, ts DESC);

            CREATE INDEX IF NOT EXISTS idx_entities_project_name_kind
            ON entities(project_id, name, kind);

            CREATE INDEX IF NOT EXISTS idx_relationships_project_from_relation
            ON relationships(project_id, from_entity, relation);

            CREATE INDEX IF NOT EXISTS idx_memory_audit_project_ts
            ON audit_events(project_id, ts DESC);
            """
        )
        self._conn.commit()

    def _relationship_unique_includes_project_id(self) -> bool:
        indexes = self._conn.execute("PRAGMA index_list('relationships')").fetchall()
        for index in indexes:
            if not bool(index["unique"]):
                continue
            columns = [
                str(row["name"])
                for row in self._conn.execute(
                    f"PRAGMA index_info('{index['name']}')"
                ).fetchall()
            ]
            if columns == ["project_id", "from_entity", "relation", "to_entity"]:
                return True
        return False

    def _ensure_relationship_partitioning(self) -> None:
        table_exists = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'relationships'"
        ).fetchone()
        if table_exists is None or self._relationship_unique_includes_project_id():
            return

        self._conn.executescript(
            """
            DROP TABLE IF EXISTS relationships_legacy;

            ALTER TABLE relationships RENAME TO relationships_legacy;

            CREATE TABLE relationships (
                project_id      TEXT NOT NULL DEFAULT 'default',
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                from_entity TEXT NOT NULL,
                relation    TEXT NOT NULL,
                to_entity   TEXT NOT NULL,
                ts          TEXT NOT NULL,
                UNIQUE(project_id, from_entity, relation, to_entity)
            );

            INSERT OR IGNORE INTO relationships (
                project_id,
                from_entity,
                relation,
                to_entity,
                ts
            )
            SELECT
                COALESCE(NULLIF(TRIM(project_id), ''), 'default'),
                from_entity,
                relation,
                to_entity,
                ts
            FROM relationships_legacy;

            DROP TABLE relationships_legacy;
            """
        )

    def _record_audit(
        self,
        project_id: str,
        action: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_events (project_id, action, details, ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                _normalize_project_id(project_id),
                action,
                json.dumps(details or {}, sort_keys=True),
                _now(),
            ),
        )

    # ------------------------------------------------------------------
    # Lessons (long-term memory)
    # ------------------------------------------------------------------

    def store_lesson(
        self,
        issue_number: int,
        outcome: str,
        summary: str,
        learnings: list[str],
        repo: str = "",
        project_id: str = "default",
    ) -> int:
        """Store a lesson from one completed issue run. Returns row id."""
        project_id = _normalize_project_id(project_id)

        cur = self._conn.execute(
            """
            INSERT INTO lessons (project_id, issue_number, repo, outcome, summary, learnings, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                issue_number,
                repo,
                outcome,
                summary,
                json.dumps(learnings),
                _now(),
            ),
        )
        self._record_audit(
            project_id,
            "store_lesson",
            {
                "issue_number": issue_number,
                "lesson_id": cur.lastrowid,
                "outcome": outcome,
                "repo": repo,
            },
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_lessons(
        self, issue_number: int, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all lessons for a given issue number."""
        project_id = _normalize_project_id(project_id)

        rows = self._conn.execute(
            "SELECT * FROM lessons WHERE issue_number = ? AND project_id = ? ORDER BY ts DESC",
            (issue_number, project_id),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def search_similar(
        self, query: str, limit: int = 5, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Full-text keyword search across lesson summaries and learnings.

        Returns up to `limit` most-recent matching rows.
        Intentionally simple — no vector search in v1.
        """
        project_id = _normalize_project_id(project_id)

        words = query.lower().split()
        if not words:
            return []
        # Build LIKE clause for each word
        conditions = " AND ".join(
            ["LOWER(summary || ' ' || learnings) LIKE ?" for _ in words]
        )
        conditions = f"({conditions}) AND project_id = ?"
        params = [f"%{w}%" for w in words]
        params.append(project_id)
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM lessons WHERE {conditions} ORDER BY ts DESC LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Short-term context (last N runs summary)
    # ------------------------------------------------------------------

    def get_recent_lessons(
        self, limit: int = 10, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return the most recent `limit` lessons across all issues."""
        project_id = _normalize_project_id(project_id)

        rows = self._conn.execute(
            "SELECT * FROM lessons WHERE project_id = ? ORDER BY ts DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Knowledge graph
    # ------------------------------------------------------------------

    def upsert_entity(
        self,
        name: str,
        kind: str,
        metadata: Optional[dict[str, Any]] = None,
        project_id: str = "default",
    ) -> None:
        """Insert or update a knowledge graph entity node."""
        project_id = _normalize_project_id(project_id)

        self._conn.execute(
            """
            INSERT INTO entities (project_id, name, kind, metadata, ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, name, kind) DO UPDATE SET metadata = excluded.metadata, ts = excluded.ts
            """,
            (project_id, name, kind, json.dumps(metadata or {}), _now()),
        )
        self._record_audit(
            project_id,
            "upsert_entity",
            {"kind": kind, "name": name},
        )
        self._conn.commit()

    def add_relationship(
        self,
        from_entity: str,
        relation: str,
        to_entity: str,
        project_id: str = "default",
    ) -> None:
        """Add or ignore a relationship edge between two entities."""
        project_id = _normalize_project_id(project_id)

        self._conn.execute(
            """
            INSERT OR IGNORE INTO relationships (project_id, from_entity, relation, to_entity, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, from_entity, relation, to_entity, _now()),
        )
        self._record_audit(
            project_id,
            "add_relationship",
            {
                "from_entity": from_entity,
                "relation": relation,
                "to_entity": to_entity,
            },
        )
        self._conn.commit()

    def get_related(
        self, entity: str, relation: Optional[str] = None, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all entities related to `entity`, optionally filtered by relation type."""
        project_id = _normalize_project_id(project_id)

        if relation:
            rows = self._conn.execute(
                "SELECT * FROM relationships WHERE from_entity = ? AND relation = ? AND project_id = ?",
                (entity, relation, project_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM relationships WHERE from_entity = ? AND project_id = ?",
                (entity, project_id),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def purge_workspace(self, project_id: str) -> dict[str, int]:
        """Deletes all records associated with a specific workspace tenant."""
        project_id = _normalize_project_id(project_id)
        cursor = self._conn.cursor()
        counts = {"lessons": 0, "entities": 0, "relationships": 0, "audit_events": 0}
        cursor.execute("DELETE FROM audit_events WHERE project_id = ?", (project_id,))
        counts["audit_events"] = cursor.rowcount
        cursor.execute("DELETE FROM relationships WHERE project_id = ?", (project_id,))
        counts["relationships"] = cursor.rowcount
        cursor.execute("DELETE FROM entities WHERE project_id = ?", (project_id,))
        counts["entities"] = cursor.rowcount
        cursor.execute("DELETE FROM lessons WHERE project_id = ?", (project_id,))
        counts["lessons"] = cursor.rowcount
        self._record_audit(project_id, "purge_workspace", {"counts": counts})
        self._conn.commit()
        return counts

    def get_audit_log(
        self,
        project_id: str = "default",
        *,
        action: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the most recent tenant-scoped audit events."""
        project_id = _normalize_project_id(project_id)
        if action:
            rows = self._conn.execute(
                """
                SELECT * FROM audit_events
                WHERE project_id = ? AND action = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (project_id, action, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM audit_events
                WHERE project_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    # Deserialize JSON fields
    for field in ("learnings", "metadata", "details"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
