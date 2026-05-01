from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factory_runtime.text_write_normalization import normalize_repo_text_for_write

from .path_guard import RepoPathGuard


@dataclass
class FilesystemService:
    repo_root: Path

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.path_guard = RepoPathGuard(self.repo_root)

    def _resolve_existing_file(self, path: str) -> Path:
        resolved = self.path_guard.resolve_relative_path(path, allow_nonexistent=False)
        if not resolved.is_file():
            raise ValueError("path must resolve to a file")
        return resolved

    def _resolve_existing_path(self, path: str) -> Path:
        return self.path_guard.resolve_relative_path(path, allow_nonexistent=False)

    def _resolve_writable_path(self, path: str) -> Path:
        resolved = self.path_guard.resolve_relative_path(path, allow_nonexistent=True)
        parent = resolved.parent
        parent.relative_to(self.repo_root)
        return resolved

    def list_dir(self, path: str = ".") -> dict[str, Any]:
        resolved = self._resolve_existing_path(path)
        if not resolved.is_dir():
            raise ValueError("path must resolve to a directory")

        children = sorted(resolved.iterdir(), key=lambda value: value.name)
        entries = [
            str(child.relative_to(self.repo_root)) + ("/" if child.is_dir() else "")
            for child in children
        ]
        return {"path": str(resolved.relative_to(self.repo_root)), "entries": entries}

    def read_text(self, path: str) -> dict[str, Any]:
        resolved = self._resolve_existing_file(path)
        content = resolved.read_text(encoding="utf-8")
        return {
            "path": str(resolved.relative_to(self.repo_root)),
            "content": content,
        }

    def write_text(
        self, path: str, content: str, create_parent: bool = True
    ) -> dict[str, Any]:
        resolved = self._resolve_writable_path(path)
        if create_parent:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        elif not resolved.parent.exists():
            raise ValueError("parent directory does not exist")

        normalized_content = normalize_repo_text_for_write(
            resolved,
            content,
            require_python_formatter=True,
        )
        resolved.write_text(normalized_content, encoding="utf-8")
        return {
            "path": str(resolved.relative_to(self.repo_root)),
            "bytes_written": len(normalized_content.encode("utf-8")),
        }

    def make_dir(self, path: str, parents: bool = True) -> dict[str, Any]:
        resolved = self._resolve_writable_path(path)
        resolved.mkdir(parents=parents, exist_ok=True)
        return {"path": str(resolved.relative_to(self.repo_root))}

    def delete_path(self, path: str, recursive: bool = False) -> dict[str, Any]:
        resolved = self._resolve_existing_path(path)
        relative = str(resolved.relative_to(self.repo_root))

        if resolved.is_dir():
            if not recursive:
                raise ValueError("directory delete requires recursive=True")
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
        return {"deleted": relative}

    def move_path(
        self, source: str, destination: str, overwrite: bool = False
    ) -> dict[str, Any]:
        src = self._resolve_existing_path(source)
        dst = self._resolve_writable_path(destination)
        src_relative = str(src.relative_to(self.repo_root))
        dst_relative = str(dst.relative_to(self.repo_root))

        if dst.exists():
            if not overwrite:
                raise ValueError("destination already exists")
            if dst.is_dir() and not src.is_dir():
                raise ValueError("destination directory cannot overwrite file target")
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()

        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return {"moved_from": src_relative, "moved_to": dst_relative}

    def copy_path(
        self, source: str, destination: str, overwrite: bool = False
    ) -> dict[str, Any]:
        src = self._resolve_existing_path(source)
        dst = self._resolve_writable_path(destination)
        src_relative = str(src.relative_to(self.repo_root))
        dst_relative = str(dst.relative_to(self.repo_root))

        if dst.exists():
            if not overwrite:
                raise ValueError("destination already exists")
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()

        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {"copied_from": src_relative, "copied_to": dst_relative}
