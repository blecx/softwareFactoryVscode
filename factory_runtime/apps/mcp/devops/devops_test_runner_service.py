from __future__ import annotations

import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_store import AuditRecord, AuditStore


class TestRunnerServiceError(RuntimeError):
    """Raised when a test profile command fails."""


@dataclass(frozen=True)
class TestProfile:
    name: str
    cwd: str
    command: list[str]
    timeout_sec: int


@dataclass
class TestRunnerService:
    repo_root: Path
    audit_dir: Path

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.audit_store = AuditStore(self.audit_dir)

        python_bin = os.getenv("TEST_RUNNER_PYTHON", "python")
        self.profiles: dict[str, TestProfile] = {
            "backend.format_lint": TestProfile(
                name="backend.format_lint",
                cwd=".",
                command=[
                    "bash",
                    "-lc",
                    f"{python_bin} -m black . && {python_bin} -m flake8 .",
                ],
                timeout_sec=900,
            ),
            "backend.tests": TestProfile(
                name="backend.tests",
                cwd=".",
                command=[python_bin, "-m", "pytest", "-v"],
                timeout_sec=1800,
            ),
            "backend.tests_quick": TestProfile(
                name="backend.tests_quick",
                cwd=".",
                command=[python_bin, "-m", "pytest", "-q", "--tb=short"],
                timeout_sec=1200,
            ),
            "frontend.lint": TestProfile(
                name="frontend.lint",
                cwd="${CLIENT_DIR:-../client}/client",
                command=["npm", "run", "lint"],
                timeout_sec=1200,
            ),
            "frontend.build": TestProfile(
                name="frontend.build",
                cwd="${CLIENT_DIR:-../client}/client",
                command=["npm", "run", "build"],
                timeout_sec=1200,
            ),
        }

    def list_profiles(self) -> dict[str, Any]:
        return {
            "profiles": [
                {
                    "name": profile.name,
                    "cwd": profile.cwd,
                    "command": profile.command,
                    "timeout_sec": profile.timeout_sec,
                }
                for profile in self.profiles.values()
            ]
        }

    def run_profile(self, profile_name: str) -> dict[str, Any]:
        profile = self.profiles.get(profile_name)
        if not profile:
            raise ValueError(f"Unknown profile: {profile_name}")

        cwd = (self.repo_root / profile.cwd).resolve()
        try:
            cwd.relative_to(self.repo_root)
        except ValueError as exc:
            sibling_root = self.repo_root.parent
            try:
                cwd.relative_to(sibling_root)
            except ValueError:
                raise ValueError(
                    "Profile cwd escapes allowed repository roots"
                ) from exc

        run_id = uuid.uuid4().hex
        start = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()

        proc = subprocess.run(
            profile.command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=profile.timeout_sec,
        )

        output = "\n".join(
            chunk for chunk in (proc.stdout.strip(), proc.stderr.strip()) if chunk
        )
        status = "ok" if proc.returncode == 0 else "error"
        duration = time.perf_counter() - start

        self.audit_store.save(
            AuditRecord(
                run_id=run_id,
                tool=profile_name,
                timestamp_utc=started_at,
                status=status,
                exit_code=proc.returncode,
                duration_sec=duration,
                cwd=str(cwd),
                command=profile.command,
                output=output,
            )
        )

        result = {
            "run_id": run_id,
            "profile": profile_name,
            "status": status,
            "exit_code": proc.returncode,
            "duration_sec": duration,
            "output": output,
        }

        if proc.returncode != 0:
            raise TestRunnerServiceError(output or f"Profile failed: {profile_name}")

        return result

    def get_run_log(self, run_id: str) -> dict[str, Any] | None:
        return self.audit_store.get(run_id)
