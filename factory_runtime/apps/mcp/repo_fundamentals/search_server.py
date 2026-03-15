import os
import re
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

from .path_guard import PathGuardError
from .search_service import SearchService


def _load_service() -> SearchService:
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
    return SearchService(repo_root=repo_root)


service = _load_service()
mcp = FastMCP("maestro Search MCP", json_response=True)


@mcp.tool()
def search_safe_root() -> dict:
    """Return effective repository root used by this server."""
    return {"repo_root": str(service.repo_root)}


@mcp.tool()
def search_list_files(
    scope: str = ".", include_glob: str = "**/*", max_results: int = 200
) -> dict:
    """List repository files within safe scope."""
    try:
        return service.list_files(
            scope=scope, include_glob=include_glob, max_results=max_results
        )
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def search_query(
    query: str,
    is_regexp: bool = False,
    scope: str = ".",
    include_glob: str = "**/*",
    max_results: int = 200,
) -> dict:
    """Search repository files with ripgrep-style options."""
    try:
        return service.search(
            query=query,
            is_regexp=is_regexp,
            scope=scope,
            include_glob=include_glob,
            max_results=max_results,
        )
    except (PathGuardError, ValueError, re.error) as exc:
        raise ValueError(str(exc)) from exc


def main() -> None:
    host = os.getenv("SEARCH_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("SEARCH_MCP_PORT", "3013"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
