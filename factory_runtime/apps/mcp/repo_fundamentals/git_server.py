import os
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

from .git_service import GitService
from .path_guard import PathGuardError


def _load_service() -> GitService:
    base_root = Path(os.getenv("REPO_FUNDAMENTALS_REPO_ROOT", "/workspace")).resolve()
    project_id = os.getenv("PROJECT_WORKSPACE_ID")
    if project_id:
        repo_root = (base_root / project_id).resolve()
        # Chroot jail ensure it does not escape base_root
        try:
            repo_root.relative_to(base_root)
        except ValueError:
            repo_root = base_root
    else:
        repo_root = base_root
    return GitService(repo_root=repo_root)


service = _load_service()
mcp = FastMCP("factory Git MCP", json_response=True)


@mcp.tool()
def git_safe_root() -> dict:
    """Return effective repository root used by this server."""
    return service.safe_root()


@mcp.tool()
def git_validate_path(path: str) -> dict:
    """Validate repository-scoped path with denylist and escape guards."""
    try:
        return service.validate_path(path)
    except PathGuardError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_status(path: str | None = None, short: bool = True) -> dict:
    """Return git status for repository or one path."""
    try:
        return service.status(path=path, short=short)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_log(max_count: int = 20, path: str | None = None) -> dict:
    """Return recent commit summaries."""
    try:
        return service.log(max_count=max_count, path=path)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_diff(path: str | None = None, staged: bool = False) -> dict:
    """Return git diff output."""
    try:
        return service.diff(path=path, staged=staged)
    except PathGuardError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_show(rev: str = "HEAD", path: str | None = None) -> dict:
    """Return git show output for revision and optional path."""
    try:
        return service.show(rev=rev, path=path)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_branch_current() -> dict:
    """Return current checked-out branch name."""
    return service.branch_current()


@mcp.tool()
def git_branch_list(all_branches: bool = False) -> dict:
    """Return local or all branch names."""
    return service.branch_list(all_branches=all_branches)


@mcp.tool()
def git_blame(
    path: str,
    rev: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> dict:
    """Return git blame porcelain output for a validated path."""
    try:
        return service.blame(
            path=path, rev=rev, line_start=line_start, line_end=line_end
        )
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_add(paths: list[str]) -> dict:
    """Stage specific paths after safety validation."""
    try:
        return service.add(paths=paths)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_commit(message: str) -> dict:
    """Create a commit with the provided message."""
    try:
        return service.commit(message=message)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def git_reset_paths(paths: list[str]) -> dict:
    """Unstage specific paths via git reset -- <paths>."""
    try:
        return service.reset_paths(paths=paths)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


def main() -> None:
    host = os.getenv("GIT_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("GIT_MCP_PORT", "3012"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
