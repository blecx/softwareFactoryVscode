from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PathGuardError(ValueError):
    """Raised when a path violates repository safety constraints."""


@dataclass(frozen=True)
class RepoPathGuard:
    repo_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_root", self.repo_root.resolve())

    def resolve_relative_path(
        self, relative_path: str, *, allow_nonexistent: bool = True
    ) -> Path:
        candidate = Path(relative_path)

        if candidate.is_absolute():
            raise PathGuardError("Absolute paths are not allowed")

        if any(part == ".." for part in candidate.parts):
            raise PathGuardError("Path traversal is not allowed")

        joined = self.repo_root / candidate
        resolved = joined.resolve(strict=False)

        try:
            relative = resolved.relative_to(self.repo_root)
        except ValueError as exc:
            raise PathGuardError("Path escapes repository root") from exc

        relative_text = relative.as_posix()
        if relative_text == "projectDocs" or relative_text.startswith("projectDocs/"):
            raise PathGuardError("Access to projectDocs is forbidden")

        if relative_text == "configs/llm.json":
            raise PathGuardError("Access to configs/llm.json is forbidden")

        if not allow_nonexistent and not resolved.exists():
            raise PathGuardError(f"Path not found: {relative_text}")

        return resolved
