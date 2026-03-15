"""Audit persistence for bash gateway runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class RunRecord:
    """Persistent run metadata."""

    run_id: str
    timestamp_utc: str
    profile: str
    script_path: str
    timeout_sec: int
    dry_run: bool
    status: str
    exit_code: int
    duration_sec: float
    cwd: str
    output: str


class AuditStore:
    """Store run records as JSON files on disk."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: RunRecord) -> Path:
        """Save run record and return file path."""
        file_path = self.base_dir / f"{record.run_id}.json"
        file_path.write_text(json.dumps(asdict(record), indent=2))
        return file_path

    def get(self, run_id: str) -> Optional[Dict]:
        """Return run record dict by run ID."""
        file_path = self.base_dir / f"{run_id}.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text())
