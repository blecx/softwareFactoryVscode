import os
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

from .filesystem_service import FilesystemService
from .path_guard import PathGuardError


def _load_service() -> FilesystemService:
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
    return FilesystemService(repo_root=repo_root)


service = _load_service()
mcp = FastMCP("maestro Filesystem MCP", json_response=True)


@mcp.tool()
def filesystem_safe_root() -> dict:
    """Return effective repository root used by this server."""
    return {"repo_root": str(service.repo_root)}


@mcp.tool()
def filesystem_list_dir(path: str = ".") -> dict:
    """List one directory under repository-safe scope."""
    try:
        return service.list_dir(path=path)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def filesystem_read_text(path: str) -> dict:
    """Read UTF-8 text file content."""
    try:
        return service.read_text(path=path)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def filesystem_write_text(path: str, content: str, create_parent: bool = True) -> dict:
    """Write UTF-8 text file content."""
    try:
        return service.write_text(
            path=path, content=content, create_parent=create_parent
        )
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def filesystem_make_dir(path: str, parents: bool = True) -> dict:
    """Create directory in safe repository scope."""
    try:
        return service.make_dir(path=path, parents=parents)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def filesystem_delete_path(path: str, recursive: bool = False) -> dict:
    """Delete file or directory (requires recursive for directories)."""
    try:
        return service.delete_path(path=path, recursive=recursive)
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def filesystem_move_path(
    source: str, destination: str, overwrite: bool = False
) -> dict:
    """Move file/directory in safe repository scope."""
    try:
        return service.move_path(
            source=source, destination=destination, overwrite=overwrite
        )
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def filesystem_copy_path(
    source: str, destination: str, overwrite: bool = False
) -> dict:
    """Copy file/directory in safe repository scope."""
    try:
        return service.copy_path(
            source=source, destination=destination, overwrite=overwrite
        )
    except (PathGuardError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


def main() -> None:
    host = os.getenv("FILESYSTEM_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("FILESYSTEM_MCP_PORT", "3014"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
