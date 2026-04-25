from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from factory_runtime.secret_safety import redact_secret_text


def redact_secrets(text: str) -> str:
    return redact_secret_text(text)


@dataclass(frozen=True)
class AuditRecord:
    run_id: str
    tool: str
    timestamp_utc: str
    status: str
    exit_code: int
    duration_sec: float
    cwd: str
    command: list[str]
    output: str


class AuditStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: AuditRecord) -> Path:
        safe_record = AuditRecord(
            run_id=record.run_id,
            tool=record.tool,
            timestamp_utc=record.timestamp_utc,
            status=record.status,
            exit_code=record.exit_code,
            duration_sec=record.duration_sec,
            cwd=record.cwd,
            command=[redact_secrets(part) for part in record.command],
            output=redact_secrets(record.output),
        )

        file_path = self.base_dir / f"{safe_record.run_id}.json"
        file_path.write_text(
            json.dumps(asdict(safe_record), indent=2), encoding="utf-8"
        )
        return file_path

    def get(self, run_id: str) -> dict[str, Any] | None:
        file_path = self.base_dir / f"{run_id}.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text(encoding="utf-8"))
