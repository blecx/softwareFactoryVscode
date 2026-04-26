"""Helpers for keeping SQLite bind mounts writable from the host runtime.

The shared MCP SQLite services run inside containers but their data lives on
host bind mounts. When those containers create or touch the SQLite files as
root, backup/restore cleanup on the host can lose write access unless the
mount ownership is handed back to the host UID/GID recorded in `.factory.env`.
"""

from __future__ import annotations

import os
from pathlib import Path

HOST_UID_ENV_KEY = "FACTORY_HOST_UID"
HOST_GID_ENV_KEY = "FACTORY_HOST_GID"
DIRECTORY_MODE = 0o775
FILE_MODE = 0o664


def _parse_optional_posix_id(env_key: str) -> int | None:
    raw_value = str(os.getenv(env_key, "")).strip()
    if not raw_value:
        return None

    try:
        value = int(raw_value)
    except ValueError:
        return None

    if value < 0:
        return None
    return value


def _align_target_permissions(path: Path, *, mode: int) -> None:
    host_uid = _parse_optional_posix_id(HOST_UID_ENV_KEY)
    host_gid = _parse_optional_posix_id(HOST_GID_ENV_KEY)

    if host_uid is not None or host_gid is not None:
        try:
            os.chown(
                path,
                host_uid if host_uid is not None else -1,
                host_gid if host_gid is not None else -1,
            )
        except OSError:
            pass

    try:
        os.chmod(path, mode)
    except OSError:
        pass


def prepare_sqlite_path(db_path: str) -> Path:
    """Create the parent directory and realign it for host-side access."""
    resolved_path = Path(db_path).expanduser()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    _align_target_permissions(resolved_path.parent, mode=DIRECTORY_MODE)
    return resolved_path


def finalize_sqlite_path(db_path: str) -> None:
    """Realign the SQLite file and sidecars after the database is opened."""
    resolved_path = Path(db_path).expanduser()
    _align_target_permissions(resolved_path.parent, mode=DIRECTORY_MODE)

    for candidate in (
        resolved_path,
        resolved_path.with_name(resolved_path.name + "-wal"),
        resolved_path.with_name(resolved_path.name + "-shm"),
    ):
        if candidate.exists():
            _align_target_permissions(candidate, mode=FILE_MODE)
