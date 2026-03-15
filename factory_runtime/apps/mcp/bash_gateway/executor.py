"""Script execution engine with timeout, dry-run, and structured results."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import uuid4

from .audit_store import AuditStore, RunRecord


@dataclass(frozen=True)
class ScriptRunResult:
    """Execution result returned by gateway executor."""

    run_id: str
    status: str
    exit_code: int
    duration_sec: float
    output: str
    log_path: str


class ScriptExecutor:
    """Execute allowlisted scripts and persist run metadata."""

    def __init__(self, repo_root: Path, audit_store: AuditStore):
        self.repo_root = repo_root
        self.audit_store = audit_store

    def execute(
        self,
        *,
        profile: str,
        script_path: str,
        absolute_script_path: Path,
        timeout_sec: int,
        dry_run: bool,
        args: List[str],
    ) -> ScriptRunResult:
        """Execute script request and persist audit record."""
        run_id = f"run-{uuid4().hex[:12]}"
        started = time.time()
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if dry_run:
            status = "simulated"
            exit_code = 0
            output = f"DRY-RUN: {script_path} {' '.join(args)}".strip()
            duration = time.time() - started
        else:
            try:
                proc = subprocess.run(
                    ["bash", str(absolute_script_path), *args],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    check=False,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                exit_code = int(proc.returncode)
                status = "success" if proc.returncode == 0 else "failed"
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") + (exc.stderr or "")
                exit_code = 124
                status = "timeout"
            duration = time.time() - started

        record = RunRecord(
            run_id=run_id,
            timestamp_utc=timestamp,
            profile=profile,
            script_path=script_path,
            timeout_sec=timeout_sec,
            dry_run=dry_run,
            status=status,
            exit_code=exit_code,
            duration_sec=duration,
            cwd=str(self.repo_root),
            output=output,
        )
        log_path = self.audit_store.save(record)

        return ScriptRunResult(
            run_id=run_id,
            status=status,
            exit_code=exit_code,
            duration_sec=duration,
            output=output,
            log_path=str(log_path),
        )
