from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .path_guard import PathGuardError, RepoPathGuard


class GitServiceError(RuntimeError):
    """Raised when a git command fails."""


@dataclass
class GitService:
    repo_root: Path

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.path_guard = RepoPathGuard(self.repo_root)

    def _run_git(self, args: list[str]) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            stdout = proc.stdout.strip()
            message = stderr or stdout or f"git {' '.join(args)} failed"
            raise GitServiceError(message)
        return proc.stdout

    def _validated_paths(self, paths: list[str]) -> list[str]:
        validated: list[str] = []
        for path in paths:
            resolved = self.path_guard.resolve_relative_path(
                path, allow_nonexistent=True
            )
            validated.append(str(resolved.relative_to(self.repo_root)))
        return validated

    def status(self, path: str | None = None, short: bool = True) -> dict[str, Any]:
        args = ["status"]
        if short:
            args.append("--short")
        if path:
            args.extend(["--", *self._validated_paths([path])])
        return {"output": self._run_git(args).strip()}

    def log(self, max_count: int = 20, path: str | None = None) -> dict[str, Any]:
        if max_count <= 0 or max_count > 200:
            raise ValueError("max_count must be between 1 and 200")

        args = ["log", f"--max-count={max_count}", "--pretty=format:%h %s"]
        if path:
            args.extend(["--", *self._validated_paths([path])])
        return {"output": self._run_git(args).strip()}

    def diff(self, path: str | None = None, staged: bool = False) -> dict[str, Any]:
        args = ["diff"]
        if staged:
            args.append("--staged")
        if path:
            args.extend(["--", *self._validated_paths([path])])
        return {"output": self._run_git(args)}

    def add(self, paths: list[str]) -> dict[str, Any]:
        if not paths:
            raise ValueError("At least one path is required")
        validated = self._validated_paths(paths)
        self._run_git(["add", "--", *validated])
        return {"added": validated}

    def commit(self, message: str) -> dict[str, Any]:
        cleaned = message.strip()
        if not cleaned:
            raise ValueError("Commit message is required")
        output = self._run_git(["commit", "-m", cleaned])
        return {"output": output.strip()}

    def reset_paths(self, paths: list[str]) -> dict[str, Any]:
        if not paths:
            raise ValueError("At least one path is required")
        validated = self._validated_paths(paths)
        self._run_git(["reset", "--", *validated])
        return {"reset": validated}

    def show(self, rev: str = "HEAD", path: str | None = None) -> dict[str, Any]:
        rev_clean = rev.strip()
        if not rev_clean:
            raise ValueError("rev is required")

        args = ["show", rev_clean]
        if path:
            args.extend(["--", *self._validated_paths([path])])
        return {"output": self._run_git(args)}

    def branch_current(self) -> dict[str, Any]:
        output = self._run_git(["branch", "--show-current"])
        return {"branch": output.strip()}

    def branch_list(self, all_branches: bool = False) -> dict[str, Any]:
        args = ["branch", "--list", "--format=%(refname:short)"]
        if all_branches:
            args.append("--all")

        output = self._run_git(args)
        branches = [line.strip() for line in output.splitlines() if line.strip()]
        return {"branches": branches, "count": len(branches)}

    def blame(
        self,
        path: str,
        rev: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
    ) -> dict[str, Any]:
        validated = self._validated_paths([path])[0]

        args = ["blame", "--line-porcelain"]
        if line_start is not None or line_end is not None:
            if line_start is None or line_end is None:
                raise ValueError("line_start and line_end must both be provided")
            if line_start <= 0 or line_end <= 0:
                raise ValueError("line_start and line_end must be >= 1")
            if line_start > line_end:
                raise ValueError("line_start must be <= line_end")
            args.extend(["-L", f"{line_start},{line_end}"])

        if rev:
            rev_clean = rev.strip()
            if not rev_clean:
                raise ValueError("rev cannot be empty")
            args.append(rev_clean)

        args.extend(["--", validated])
        output = self._run_git(args)
        return {"path": validated, "output": output}

    def safe_root(self) -> dict[str, Any]:
        return {"repo_root": str(self.repo_root)}

    def validate_path(self, path: str) -> dict[str, Any]:
        resolved = self.path_guard.resolve_relative_path(path, allow_nonexistent=True)
        return {
            "path": path,
            "resolved": str(resolved),
            "relative": str(resolved.relative_to(self.repo_root)),
        }
