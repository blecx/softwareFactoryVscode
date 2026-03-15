from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_TOKEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(GH_TOKEN|GITHUB_TOKEN)\s*=\s*[^\s\"]+"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
]


def redact_secrets(text: str) -> str:
    value = text or ""
    for pattern in _TOKEN_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


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
            command=record.command,
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
