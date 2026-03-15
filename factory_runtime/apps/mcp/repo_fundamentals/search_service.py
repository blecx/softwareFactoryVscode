from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .path_guard import RepoPathGuard


@dataclass
class SearchService:
    repo_root: Path
    forbidden_globs: tuple[str, ...] = ("!projectDocs/**", "!configs/llm.json")

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.path_guard = RepoPathGuard(self.repo_root)

    def _resolve_scope_dir(self, scope: str) -> tuple[Path, str]:
        resolved_scope = self.path_guard.resolve_relative_path(
            scope, allow_nonexistent=False
        )
        if not resolved_scope.is_dir():
            raise ValueError("scope must resolve to a directory")
        return resolved_scope, str(resolved_scope.relative_to(self.repo_root))

    def _rg_base_args(self, include_glob: str) -> list[str]:
        args = ["rg", "--hidden"]
        if include_glob:
            args.extend(["-g", include_glob])
        for forbidden_glob in self.forbidden_globs:
            args.extend(["-g", forbidden_glob])
        return args

    def _run_rg(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                "ripgrep (rg) is not installed in this environment"
            ) from exc

    def _list_files_rg(
        self, scope_relative: str, include_glob: str, max_results: int
    ) -> list[str]:
        args = [*self._rg_base_args(include_glob), "--files", scope_relative]
        proc = self._run_rg(args)

        if proc.returncode not in (0, 1):
            stderr = proc.stderr.strip() or proc.stdout.strip() or "rg --files failed"
            raise ValueError(stderr)

        files = [
            line.strip().removeprefix("./")
            for line in proc.stdout.splitlines()
            if line.strip()
        ]
        return files[:max_results]

    def list_files(
        self, scope: str = ".", include_glob: str = "**/*", max_results: int = 200
    ) -> dict[str, Any]:
        if max_results <= 0 or max_results > 2000:
            raise ValueError("max_results must be between 1 and 2000")

        _, scope_relative = self._resolve_scope_dir(scope)
        files = self._list_files_rg(
            scope_relative=scope_relative,
            include_glob=include_glob,
            max_results=max_results,
        )
        return {
            "count": len(files),
            "files": files,
        }

    def search(
        self,
        query: str,
        *,
        is_regexp: bool = False,
        scope: str = ".",
        include_glob: str = "**/*",
        max_results: int = 200,
    ) -> dict[str, Any]:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query is required")
        if max_results <= 0 or max_results > 2000:
            raise ValueError("max_results must be between 1 and 2000")
        _, scope_relative = self._resolve_scope_dir(scope)

        if is_regexp:
            try:
                re.compile(query_text)
            except re.error as exc:
                raise ValueError(str(exc)) from exc

        args = [
            *self._rg_base_args(include_glob),
            "--json",
            "--line-number",
            "--ignore-case",
        ]
        if not is_regexp:
            args.append("--fixed-strings")
        args.extend([query_text, scope_relative])

        proc = self._run_rg(args)
        if proc.returncode not in (0, 1):
            stderr = proc.stderr.strip() or proc.stdout.strip() or "rg query failed"
            raise ValueError(stderr)

        matches: list[dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            if len(matches) >= max_results:
                break

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if payload.get("type") != "match":
                continue

            data = payload.get("data", {})
            path_info = data.get("path", {})
            line_number = data.get("line_number")
            lines_info = data.get("lines", {})

            path_text = path_info.get("text")
            line_text = lines_info.get("text")
            if (
                not isinstance(path_text, str)
                or not isinstance(line_number, int)
                or not isinstance(line_text, str)
            ):
                continue

            matches.append(
                {
                    "path": path_text.removeprefix("./"),
                    "line": line_number,
                    "text": line_text.rstrip("\n"),
                }
            )

        return {
            "query": query_text,
            "is_regexp": is_regexp,
            "count": len(matches),
            "matches": matches,
        }
