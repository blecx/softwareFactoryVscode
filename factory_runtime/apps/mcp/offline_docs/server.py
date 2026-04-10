import os
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

from .service import OfflineDocsService, OfflineDocsServiceError


def _load_service() -> OfflineDocsService:
    repo_root = Path(os.getenv("OFFLINE_DOCS_MCP_REPO_ROOT", "/workspace")).resolve()
    index_db = Path(
        os.getenv(
            "OFFLINE_DOCS_INDEX_DB",
            str(
                repo_root
                / ".copilot/softwareFactoryVscode/.tmp"
                / "mcp-offline-docs"
                / "docs_index.db"
            ),
        )
    ).resolve()
    source_env = os.getenv(
        "OFFLINE_DOCS_INDEX_SOURCES", "docs,README.md,QUICKSTART.md,templates"
    )
    source_paths = [item.strip() for item in source_env.split(",") if item.strip()]
    return OfflineDocsService(
        repo_root=repo_root, index_db_path=index_db, source_paths=source_paths
    )


service = _load_service()
mcp = FastMCP("factory Offline Docs MCP", json_response=True)


@mcp.tool()
def offline_docs_index_rebuild() -> dict:
    """Rebuild offline docs index from configured local repository sources."""
    try:
        return service.rebuild_index()
    except (OfflineDocsServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def offline_docs_index_stats() -> dict:
    """Return index statistics and configured sources."""
    return service.stats()


@mcp.tool()
def offline_docs_search(query: str, max_results: int = 20) -> dict:
    """Search indexed local docs without any network dependency."""
    try:
        return service.search(query=query, max_results=max_results)
    except (OfflineDocsServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def offline_docs_read(path: str, start_line: int = 1, end_line: int = 200) -> dict:
    """Read indexed local doc content by path and line range."""
    try:
        return service.read_document(
            path=path, start_line=start_line, end_line=end_line
        )
    except (OfflineDocsServiceError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


def main() -> None:
    host = os.getenv("OFFLINE_DOCS_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("OFFLINE_DOCS_MCP_PORT", "3017"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
