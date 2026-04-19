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
from pathlib import Path
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


def _normalize_project_id(project_id: str) -> str:
    normalized = str(project_id).strip()
    if not normalized:
        raise ValueError("project_id must be a non-empty string")
    return normalized


RUN_NOT_FOUND_FOR_PROJECT_ERROR = (
    "Run not found for project. Confirm the tenant identity matches the target run."
)


class InvalidStatusTransitionError(ValueError):
    pass


class AgentBus:
    """SQLite-backed context bus for FACTORY agent task runs."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        if self._db_path != ":memory:":
            Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
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
                project_id      TEXT NOT NULL DEFAULT 'default',
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
                project_id      TEXT NOT NULL DEFAULT 'default',
                filepath        TEXT NOT NULL,
                content_before  TEXT,
                content_after   TEXT,
                ts              TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS validation_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                project_id      TEXT NOT NULL DEFAULT 'default',
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
                project_id      TEXT NOT NULL DEFAULT 'default',
                label           TEXT NOT NULL,
                metadata        TEXT NOT NULL DEFAULT '{}',
                ts              TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id      TEXT NOT NULL DEFAULT 'default',
                run_id          TEXT,
                action          TEXT NOT NULL,
                details         TEXT NOT NULL DEFAULT '{}',
                ts              TEXT NOT NULL
            );
            """
        )
        self._ensure_project_partition_columns()
        self._backfill_project_partition_columns()
        self._conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_task_runs_project_status_created
            ON task_runs(project_id, status, created_ts);

            CREATE INDEX IF NOT EXISTS idx_plans_project_run
            ON plans(project_id, run_id);

            CREATE INDEX IF NOT EXISTS idx_file_snapshots_project_run_ts
            ON file_snapshots(project_id, run_id, ts DESC);

            CREATE INDEX IF NOT EXISTS idx_validation_results_project_run_ts
            ON validation_results(project_id, run_id, ts DESC);

            CREATE INDEX IF NOT EXISTS idx_checkpoints_project_run_ts
            ON checkpoints(project_id, run_id, ts DESC);

            CREATE INDEX IF NOT EXISTS idx_agent_bus_audit_project_run_ts
            ON audit_events(project_id, run_id, ts DESC);
            """
        )
        self._conn.commit()

    def _table_has_column(self, table_name: str, column_name: str) -> bool:
        rows = self._conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        return any(str(row["name"]) == column_name for row in rows)

    def _ensure_project_partition_columns(self) -> None:
        for table_name in (
            "plans",
            "file_snapshots",
            "validation_results",
            "checkpoints",
        ):
            if self._table_has_column(table_name, "project_id"):
                continue
            self._conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN project_id TEXT NOT NULL DEFAULT 'default'"
            )

    def _backfill_project_partition_columns(self) -> None:
        for table_name in (
            "plans",
            "file_snapshots",
            "validation_results",
            "checkpoints",
        ):
            if not self._table_has_column(table_name, "project_id"):
                continue
            self._conn.execute(
                f"""
                UPDATE {table_name}
                SET project_id = COALESCE(
                    (
                        SELECT task_runs.project_id
                        FROM task_runs
                        WHERE task_runs.run_id = {table_name}.run_id
                    ),
                    project_id,
                    'default'
                )
                WHERE project_id IS NULL
                   OR TRIM(project_id) = ''
                   OR project_id = 'default'
                """
            )

    def _record_audit(
        self,
        project_id: str,
        action: str,
        *,
        run_id: str | None = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_events (project_id, run_id, action, details, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _normalize_project_id(project_id),
                run_id,
                action,
                json.dumps(details or {}, sort_keys=True),
                _now(),
            ),
        )

    # ------------------------------------------------------------------
    # Task runs
    # ------------------------------------------------------------------

    def create_run(
        self, issue_number: int, repo: str = "", project_id: str = "default"
    ) -> str:
        """Create a new task run and return its run_id."""
        project_id = _normalize_project_id(project_id)
        run_id = str(uuid4())
        ts = _now()
        self._conn.execute(
            """
            INSERT INTO task_runs (run_id, project_id, issue_number, repo, status, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, 'created', ?, ?)
            """,
            (run_id, project_id, issue_number, repo, ts, ts),
        )
        self._record_audit(
            project_id,
            "create_run",
            run_id=run_id,
            details={
                "issue_number": issue_number,
                "repo": repo,
                "status": "created",
            },
        )
        self._conn.commit()
        return run_id

    def get_run(
        self, run_id: str, project_id: str = "default"
    ) -> Optional[dict[str, Any]]:
        """Return run metadata or None if not found."""
        project_id = _normalize_project_id(project_id)
        row = self._conn.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND project_id = ?",
            (run_id, project_id),
        ).fetchone()
        return dict(row) if row else None

    def set_status(self, run_id: str, status: str, project_id: str = "default") -> None:
        """Transition run to a new status. Raises InvalidStatusTransitionError on bad transitions."""
        project_id = _normalize_project_id(project_id)
        run = self.get_run(run_id, project_id=project_id)
        if run is None:
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
        current = run["status"]
        allowed = _VALID_TRANSITIONS.get(current, set())
        if status not in allowed:
            raise InvalidStatusTransitionError(
                f"Cannot transition '{current}' → '{status}'. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
            )
        self._conn.execute(
            "UPDATE task_runs SET status = ?, updated_ts = ? WHERE run_id = ? AND project_id = ?",
            (status, _now(), run_id, project_id),
        )
        self._record_audit(
            project_id,
            "set_status",
            run_id=run_id,
            details={"from_status": current, "to_status": status},
        )
        self._conn.commit()

    def list_pending_approval(
        self, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all runs currently awaiting human approval."""
        project_id = _normalize_project_id(project_id)
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
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
        self._conn.execute(
            """
            INSERT INTO plans (
                run_id,
                project_id,
                goal,
                files,
                acceptance_criteria,
                validation_cmds,
                estimated_minutes,
                ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                project_id = excluded.project_id,
                goal = excluded.goal,
                files = excluded.files,
                acceptance_criteria = excluded.acceptance_criteria,
                validation_cmds = excluded.validation_cmds,
                estimated_minutes = excluded.estimated_minutes,
                ts = excluded.ts
            """,
            (
                run_id,
                project_id,
                goal,
                json.dumps(files),
                json.dumps(acceptance_criteria),
                json.dumps(validation_cmds),
                estimated_minutes,
                _now(),
            ),
        )
        self._record_audit(
            project_id,
            "write_plan",
            run_id=run_id,
            details={
                "acceptance_criteria_count": len(acceptance_criteria),
                "files_count": len(files),
                "validation_command_count": len(validation_cmds),
            },
        )
        self._conn.commit()

    def approve_run(
        self, run_id: str, feedback: str = "", project_id: str = "default"
    ) -> None:
        """Mark the plan as approved and update run status to 'approved'."""
        project_id = _normalize_project_id(project_id)
        # In sqlite we can't easily JOIN an UPDATE, so let's check permission first.
        if not self.get_run(run_id, project_id=project_id):
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
        self._conn.execute(
            "UPDATE plans SET approved = 1, feedback = ? WHERE run_id = ? AND project_id = ?",
            (feedback, run_id, project_id),
        )
        self._record_audit(
            project_id,
            "approve_run",
            run_id=run_id,
            details={"feedback_present": bool(feedback.strip())},
        )
        self.set_status(run_id, "approved", project_id=project_id)

    def get_plan(
        self, run_id: str, project_id: str = "default"
    ) -> Optional[dict[str, Any]]:
        """Return the plan for a run, with JSON fields deserialized."""
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            return None
        row = self._conn.execute(
            "SELECT * FROM plans WHERE run_id = ? AND project_id = ?",
            (run_id, project_id),
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
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
        self._conn.execute(
            """
            INSERT INTO file_snapshots (run_id, project_id, filepath, content_before, content_after, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, project_id, filepath, content_before, content_after, _now()),
        )
        self._record_audit(
            project_id,
            "write_snapshot",
            run_id=run_id,
            details={"filepath": filepath},
        )
        self._conn.commit()

    def get_snapshots(
        self, run_id: str, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all file snapshots for a run."""
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM file_snapshots WHERE run_id = ? AND project_id = ? ORDER BY ts ASC",
            (run_id, project_id),
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
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
        self._conn.execute(
            """
            INSERT INTO validation_results (run_id, project_id, command, stdout, stderr, exit_code, passed, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_id,
                command,
                stdout,
                stderr,
                exit_code,
                int(passed),
                _now(),
            ),
        )
        self._record_audit(
            project_id,
            "write_validation",
            run_id=run_id,
            details={
                "command": command,
                "exit_code": exit_code,
                "passed": bool(passed),
            },
        )
        self._conn.commit()

    def get_validations(
        self, run_id: str, limit: int = 10, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return the most recent validation results for a run."""
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM validation_results WHERE run_id = ? AND project_id = ?
            ORDER BY ts DESC LIMIT ?
            """,
            (run_id, project_id, limit),
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
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
        self._conn.execute(
            """
            INSERT INTO checkpoints (run_id, project_id, label, metadata, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, project_id, label, json.dumps(metadata or {}), _now()),
        )
        self._record_audit(
            project_id,
            "write_checkpoint",
            run_id=run_id,
            details={"label": label},
        )
        self._conn.commit()

    def get_checkpoints(
        self, run_id: str, project_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return all checkpoints for a run in chronological order."""
        project_id = _normalize_project_id(project_id)
        if self.get_run(run_id, project_id=project_id) is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM checkpoints WHERE run_id = ? AND project_id = ? ORDER BY ts ASC",
            (run_id, project_id),
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
            raise ValueError(RUN_NOT_FOUND_FOR_PROJECT_ERROR)
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
        project_id = _normalize_project_id(project_id)
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
            "audit_events": 0,
        }
        cursor.execute("DELETE FROM audit_events WHERE project_id = ?", (project_id,))
        counts["audit_events"] = cursor.rowcount
        if not run_ids:
            self._record_audit(
                project_id, "purge_workspace", details={"counts": counts}
            )
            self._conn.commit()
            return counts

        placeholders = ",".join("?" * len(run_ids))

        cursor.execute(
            f"DELETE FROM checkpoints WHERE project_id = ? AND run_id IN ({placeholders})",
            (project_id, *run_ids),
        )
        counts["checkpoints"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM validation_results WHERE project_id = ? AND run_id IN ({placeholders})",
            (project_id, *run_ids),
        )
        counts["validations"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM file_snapshots WHERE project_id = ? AND run_id IN ({placeholders})",
            (project_id, *run_ids),
        )
        counts["snapshots"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM plans WHERE project_id = ? AND run_id IN ({placeholders})",
            (project_id, *run_ids),
        )
        counts["plans"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM task_runs WHERE project_id = ? AND run_id IN ({placeholders})",
            (project_id, *run_ids),
        )
        counts["runs"] = cursor.rowcount

        self._record_audit(project_id, "purge_workspace", details={"counts": counts})
        self._conn.commit()
        return counts

    def get_audit_log(
        self,
        project_id: str = "default",
        *,
        run_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the most recent tenant-scoped audit events."""
        project_id = _normalize_project_id(project_id)
        if run_id:
            rows = self._conn.execute(
                """
                SELECT * FROM audit_events
                WHERE project_id = ? AND run_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (project_id, run_id, limit),
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
        result = [dict(r) for r in rows]
        for item in result:
            if isinstance(item.get("details"), str):
                try:
                    item["details"] = json.loads(item["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result
