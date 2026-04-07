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
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    """SQLite-backed memory store for FACTORY agent memory layers."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.row_factory = sqlite3.Row
        self._migrate()

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
                UNIQUE(from_entity, relation, to_entity)
            );
            """
        )
        self._conn.commit()

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
        import os

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
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_lessons(self, issue_number: int, project_id: str = "default") -> list[dict[str, Any]]:
        """Return all lessons for a given issue number."""
        import os

        rows = self._conn.execute(
            "SELECT * FROM lessons WHERE issue_number = ? AND project_id = ? ORDER BY ts DESC",
            (issue_number, project_id),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def search_similar(self, query: str, limit: int = 5, project_id: str = "default") -> list[dict[str, Any]]:
        """Full-text keyword search across lesson summaries and learnings.

        Returns up to `limit` most-recent matching rows.
        Intentionally simple — no vector search in v1.
        """
        import os

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

    def get_recent_lessons(self, limit: int = 10, project_id: str = "default") -> list[dict[str, Any]]:
        """Return the most recent `limit` lessons across all issues."""
        import os

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
    ) -> None:
        """Insert or update a knowledge graph entity node."""
        import os

        self._conn.execute(
            """
            INSERT INTO entities (project_id, name, kind, metadata, ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, name, kind) DO UPDATE SET metadata = excluded.metadata, ts = excluded.ts
            """,
            (project_id, name, kind, json.dumps(metadata or {}), _now()),
        )
        self._conn.commit()

    def add_relationship(self, from_entity: str, relation: str, to_entity: str, project_id: str = "default") -> None:
        """Add or ignore a relationship edge between two entities."""
        import os

        self._conn.execute(
            """
            INSERT OR IGNORE INTO relationships (project_id, from_entity, relation, to_entity, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, from_entity, relation, to_entity, _now()),
        )
        self._conn.commit()

    def get_related(
        self, entity: str, relation: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Return all entities related to `entity`, optionally filtered by relation type."""
        import os

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

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    # Deserialize JSON fields
    for field in ("learnings", "metadata"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


    def purge_workspace(self, project_id: str) -> dict[str, int]:
        """Deletes all records associated with a specific workspace tenant."""
        cursor = self._conn.cursor()
        
        counts = {"lessons": 0, "entities": 0, "relationships": 0}
        
        cursor.execute("DELETE FROM relationships WHERE project_id = ?", (project_id,))
        counts["relationships"] = cursor.rowcount
        
        cursor.execute("DELETE FROM entities WHERE project_id = ?", (project_id,))
        counts["entities"] = cursor.rowcount
        
        cursor.execute("DELETE FROM lessons WHERE project_id = ?", (project_id,))
        counts["lessons"] = cursor.rowcount
        
        self._conn.commit()
        return counts
