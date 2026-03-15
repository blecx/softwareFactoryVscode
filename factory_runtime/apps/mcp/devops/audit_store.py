from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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
        file_path = self.base_dir / f"{record.run_id}.json"
        file_path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        return file_path

    def get(self, run_id: str) -> dict[str, Any] | None:
        file_path = self.base_dir / f"{run_id}.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text(encoding="utf-8"))
