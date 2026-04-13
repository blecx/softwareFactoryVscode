"""AgentBus - SQLite backend for the mcp-agent-bus server.

Tables:
  task_runs          : one row per agent task run
  plans              : approved implementation plan (one per run)
  file_snapshots     : before/after content for modified files
  validation_results : test/lint command outputs
  checkpoints        : named milestones within a run

Status lifecycle (enforced server-side):
  created → routing → planning → awaiting_approval → approved
         → coding → validating → reviewing → pr_created → done
  Any state → failed

Design: single SQLite file, no external deps, easy to wipe/reset.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

# ---------------------------------------------------------------------------
# Allowed status transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "created": {"routing", "failed"},
    "routing": {"planning", "failed"},
    "planning": {"awaiting_approval", "failed"},
    "awaiting_approval": {"approved", "failed"},
    "approved": {"coding", "failed"},
    "coding": {"validating", "failed"},
    "validating": {"reviewing", "coding", "failed"},  # retry → back to coding
    "reviewing": {"pr_created", "failed"},
    "pr_created": {"done", "failed"},
    "done": set(),
    "failed": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvalidStatusTransitionError(ValueError):
    pass


class AgentBus:
    """SQLite-backed context bus for FACTORY agent task runs."""

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
            CREATE TABLE IF NOT EXISTS task_runs (
                run_id          TEXT PRIMARY KEY,
                project_id      TEXT NOT NULL DEFAULT 'default',
                issue_number    INTEGER NOT NULL,
                repo            TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'created',
                complexity_score INTEGER,
                model_tier      TEXT,
                created_ts      TEXT NOT NULL,
                updated_ts      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plans (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL UNIQUE,
                goal            TEXT NOT NULL,
                files           TEXT NOT NULL DEFAULT '[]',  -- JSON list of paths
                acceptance_criteria TEXT NOT NULL DEFAULT '[]',
                validation_cmds TEXT NOT NULL DEFAULT '[]',
                estimated_minutes INTEGER,
                approved        INTEGER NOT NULL DEFAULT 0,
                feedback        TEXT NOT NULL DEFAULT '',
                ts              TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS file_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                filepath        TEXT NOT NULL,
                content_before  TEXT,
                content_after   TEXT,
                ts              TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS validation_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                command         TEXT NOT NULL,
                stdout          TEXT NOT NULL DEFAULT '',
                stderr          TEXT NOT NULL DEFAULT '',
                exit_code       INTEGER NOT NULL,
                passed          INTEGER NOT NULL,
                ts              TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                label           TEXT NOT NULL,
                metadata        TEXT NOT NULL DEFAULT '{}',
                ts              TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
            );
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Task runs
    # ------------------------------------------------------------------

    def create_run(
        self, issue_number: int, repo: str = "", project_id: str = "default"
    ) -> str:
        """Create a new task run and return its run_id."""
        run_id = str(uuid4())
        ts = _now()
        self._conn.execute(
            """
            INSERT INTO task_runs (run_id, project_id, issue_number, repo, status, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, 'created', ?, ?)
            """,
            (run_id, project_id, issue_number, repo, ts, ts),
        )
        self._conn.commit()
        return run_id

    def get_run(
        self, run_id: str, project_id: str = "default"
    ) -> Optional[dict[str, Any]]:
        """Return run metadata or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND project_id = ?",
            (run_id, project_id),
        ).fetchone()
        return dict(row) if row else None

    def set_status(self, run_id: str, status: str, project_id: str = "default") -> None:
        """Transition run to a new status. Raises InvalidStatusTransitionError on bad transitions."""
        run = self.get_run(run_id, project_id=project_id)
        if run is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        current = run["status"]
        allowed = _VALID_TRANSITIONS.get(current, set())
        if status not in allowed:
            raise InvalidStatusTransitionError(
                f"Cannot transition '{current}' → '{status}'. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
            )
        self._conn.execute(
            "UPDATE task_runs SET status = ?, updated_ts = ? WHERE run_id = ?",
            (status, _now(), run_id),
        )
        self._conn.commit()

    def list_pending_approval(
        self, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all runs currently awaiting human approval."""
        rows = self._conn.execute(
            "SELECT * FROM task_runs WHERE status = 'awaiting_approval' AND project_id = ? ORDER BY created_ts ASC",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------

    def write_plan(
        self,
        run_id: str,
        goal: str,
        files: list[str],
        acceptance_criteria: list[str],
        validation_cmds: list[str],
        estimated_minutes: Optional[int] = None,
        project_id: str = "default",
    ) -> None:
        """Write (or replace) the implementation plan for a run."""
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError("Run not found for project.")
        self._conn.execute(
            """
            INSERT INTO plans (run_id, goal, files, acceptance_criteria, validation_cmds, estimated_minutes, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                goal = excluded.goal,
                files = excluded.files,
                acceptance_criteria = excluded.acceptance_criteria,
                validation_cmds = excluded.validation_cmds,
                estimated_minutes = excluded.estimated_minutes,
                ts = excluded.ts
            """,
            (
                run_id,
                goal,
                json.dumps(files),
                json.dumps(acceptance_criteria),
                json.dumps(validation_cmds),
                estimated_minutes,
                _now(),
            ),
        )
        self._conn.commit()

    def approve_run(
        self, run_id: str, feedback: str = "", project_id: str = "default"
    ) -> None:
        """Mark the plan as approved and update run status to 'approved'."""
        # In sqlite we can't easily JOIN an UPDATE, so let's check permission first.
        if not self.get_run(run_id, project_id=project_id):
            raise ValueError("Run not found for project.")
        self._conn.execute(
            "UPDATE plans SET approved = 1, feedback = ? WHERE run_id = ?",
            (feedback, run_id),
        )
        self.set_status(run_id, "approved", project_id=project_id)

    def get_plan(
        self, run_id: str, project_id: str = "default"
    ) -> Optional[dict[str, Any]]:
        """Return the plan for a run, with JSON fields deserialized."""
        if self.get_run(run_id, project_id=project_id) is None:
            return None
        row = self._conn.execute(
            "SELECT * FROM plans WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        for field in ("files", "acceptance_criteria", "validation_cmds"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    # ------------------------------------------------------------------
    # File snapshots
    # ------------------------------------------------------------------

    def write_snapshot(
        self,
        run_id: str,
        filepath: str,
        content_before: Optional[str],
        content_after: Optional[str],
        project_id: str = "default",
    ) -> None:
        """Record before/after content for a file modified during a run."""
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError("Run not found for project.")
        self._conn.execute(
            """
            INSERT INTO file_snapshots (run_id, filepath, content_before, content_after, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, filepath, content_before, content_after, _now()),
        )
        self._conn.commit()

    def get_snapshots(
        self, run_id: str, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all file snapshots for a run."""
        if self.get_run(run_id, project_id=project_id) is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM file_snapshots WHERE run_id = ? ORDER BY ts ASC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Validation results
    # ------------------------------------------------------------------

    def write_validation(
        self,
        run_id: str,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        passed: bool,
        project_id: str = "default",
    ) -> None:
        """Record the result of a validation command (test/lint run)."""
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError("Run not found for project.")
        self._conn.execute(
            """
            INSERT INTO validation_results (run_id, command, stdout, stderr, exit_code, passed, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, command, stdout, stderr, exit_code, int(passed), _now()),
        )
        self._conn.commit()

    def get_validations(
        self, run_id: str, limit: int = 10, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return the most recent validation results for a run."""
        if self.get_run(run_id, project_id=project_id) is None:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM validation_results WHERE run_id = ?
            ORDER BY ts DESC LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
        results = [dict(r) for r in rows]
        for r in results:
            r["passed"] = bool(r["passed"])
        return results

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def write_checkpoint(
        self,
        run_id: str,
        label: str,
        metadata: Optional[dict[str, Any]] = None,
        project_id: str = "default",
    ) -> None:
        """Record a named milestone checkpoint within a run."""
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError("Run not found for project.")
        self._conn.execute(
            """
            INSERT INTO checkpoints (run_id, label, metadata, ts)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, label, json.dumps(metadata or {}), _now()),
        )
        self._conn.commit()

    def get_checkpoints(
        self, run_id: str, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all checkpoints for a run in chronological order."""
        if self.get_run(run_id, project_id=project_id) is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM checkpoints WHERE run_id = ? ORDER BY ts ASC",
            (run_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("metadata"), str):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Context packet (the key FACTORY primitive)
    # ------------------------------------------------------------------

    def read_context_packet(
        self, run_id: str, project_id: str = "default"
    ) -> dict[str, Any]:
        """Return all run data in one call - the core FACTORY primitive.

        Any agent can call this once to get the full issue context,
        approved plan, all file snapshots, and recent validation results.
        Nothing is lost between agent phases.

        Returns:
            {
              "run": {...},
              "plan": {...} | None,
              "file_snapshots": [...],
              "validation_results": [...],   # last 3 results
              "checkpoints": [...]
            }
        """
        run = self.get_run(run_id, project_id=project_id)
        if run is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        return {
            "run": run,
            "plan": self.get_plan(run_id, project_id=project_id),
            "file_snapshots": self.get_snapshots(run_id, project_id=project_id),
            "validation_results": self.get_validations(
                run_id,
                limit=3,
                project_id=project_id,
            ),
            "checkpoints": self.get_checkpoints(run_id, project_id=project_id),
        }

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    def purge_workspace(self, project_id: str) -> dict[str, int]:
        """Deletes all records associated with a specific workspace tenant."""
        cursor = self._conn.cursor()

        # Find all run IDs for this tenant
        cursor.execute(
            "SELECT run_id FROM task_runs WHERE project_id = ?", (project_id,)
        )
        run_ids = [row[0] for row in cursor.fetchall()]

        counts = {
            "runs": 0,
            "plans": 0,
            "snapshots": 0,
            "validations": 0,
            "checkpoints": 0,
        }
        if not run_ids:
            return counts

        placeholders = ",".join("?" * len(run_ids))

        cursor.execute(
            f"DELETE FROM checkpoints WHERE run_id IN ({placeholders})", run_ids
        )
        counts["checkpoints"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM validation_results WHERE run_id IN ({placeholders})", run_ids
        )
        counts["validations"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM file_snapshots WHERE run_id IN ({placeholders})", run_ids
        )
        counts["snapshots"] = cursor.rowcount

        cursor.execute(f"DELETE FROM plans WHERE run_id IN ({placeholders})", run_ids)
        counts["plans"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM task_runs WHERE run_id IN ({placeholders})", run_ids
        )
        counts["runs"] = cursor.rowcount

        self._conn.commit()
        return counts
