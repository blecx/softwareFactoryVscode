from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_store import AuditRecord, AuditStore


class DockerComposeServiceError(RuntimeError):
    """Raised when docker compose command fails."""


@dataclass
class DockerComposeService:
    repo_root: Path
    compose_targets: dict[str, str]
    audit_dir: Path

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.audit_store = AuditStore(self.audit_dir)

    def _resolve_compose_file(self, target: str) -> str:
        compose_file = self.compose_targets.get(target)
        if not compose_file:
            raise ValueError(f"Unknown compose target: {target}")

        candidate = (self.repo_root / compose_file).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise ValueError("Compose file escapes repository root") from exc

        if not candidate.exists():
            raise ValueError(f"Compose file not found: {compose_file}")

        relative = candidate.relative_to(self.repo_root).as_posix()
        if relative == "projectDocs" or relative.startswith("projectDocs/"):
            raise ValueError("Compose files under projectDocs are forbidden")
        if relative == "configs/llm.json":
            raise ValueError("configs/llm.json is forbidden")

        return relative

    def _run(self, tool: str, command: list[str]) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        start = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()

        proc = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        output = "\n".join(
            chunk for chunk in (proc.stdout.strip(), proc.stderr.strip()) if chunk
        )
        status = "ok" if proc.returncode == 0 else "error"
        duration = time.perf_counter() - start

        self.audit_store.save(
            AuditRecord(
                run_id=run_id,
                tool=tool,
                timestamp_utc=started_at,
                status=status,
                exit_code=proc.returncode,
                duration_sec=duration,
                cwd=str(self.repo_root),
                command=command,
                output=output,
            )
        )

        if proc.returncode != 0:
            raise DockerComposeServiceError(
                output or f"Command failed: {' '.join(command)}"
            )

        return {
            "run_id": run_id,
            "status": status,
            "exit_code": proc.returncode,
            "duration_sec": duration,
            "output": output,
        }

    def list_targets(self) -> dict[str, Any]:
        return {
            "targets": [
                {"name": key, "compose_file": value}
                for key, value in sorted(self.compose_targets.items())
            ]
        }

    def compose_ps(self, target: str) -> dict[str, Any]:
        compose_file = self._resolve_compose_file(target)
        return self._run(
            tool="compose_ps",
            command=["docker", "compose", "-f", compose_file, "ps", "--all"],
        )

    def compose_up(
        self, target: str, build: bool = False, detach: bool = True
    ) -> dict[str, Any]:
        compose_file = self._resolve_compose_file(target)
        command = ["docker", "compose", "-f", compose_file, "up"]
        if build:
            command.append("--build")
        if detach:
            command.append("-d")
        return self._run(tool="compose_up", command=command)

    def compose_down(self, target: str, remove_orphans: bool = True) -> dict[str, Any]:
        compose_file = self._resolve_compose_file(target)
        command = ["docker", "compose", "-f", compose_file, "down"]
        if remove_orphans:
            command.append("--remove-orphans")
        return self._run(tool="compose_down", command=command)

    def compose_logs(
        self, target: str, service: str | None = None, tail: int = 200
    ) -> dict[str, Any]:
        if tail <= 0 or tail > 5000:
            raise ValueError("tail must be between 1 and 5000")

        compose_file = self._resolve_compose_file(target)
        command = [
            "docker",
            "compose",
            "-f",
            compose_file,
            "logs",
            "--no-color",
            "--tail",
            str(tail),
        ]
        if service:
            command.append(service)
        return self._run(tool="compose_logs", command=command)

    def container_health(self, target: str) -> dict[str, Any]:
        compose_file = self._resolve_compose_file(target)
        raw = self._run(
            tool="container_health",
            command=["docker", "compose", "-f", compose_file, "ps", "--format", "json"],
        )

        containers: list[dict[str, Any]] = []
        for line in raw["output"].splitlines():
            entry = line.strip()
            if not entry:
                continue
            try:
                data = json.loads(entry)
            except json.JSONDecodeError:
                continue
            containers.append(
                {
                    "name": data.get("Name"),
                    "service": data.get("Service"),
                    "state": data.get("State"),
                    "health": data.get("Health"),
                    "status": data.get("Status"),
                }
            )

        return {
            "run_id": raw["run_id"],
            "count": len(containers),
            "containers": containers,
        }

    def get_run_log(self, run_id: str) -> dict[str, Any] | None:
        return self.audit_store.get(run_id)
