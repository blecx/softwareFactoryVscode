"""FastMCP server for mcp-memory.

Exposes MemoryStore through 5 MCP tools:
  memory_store_lesson       — write a lesson after an issue run
  memory_get_lessons        — read all lessons for one issue
  memory_search_similar     — keyword search across past lessons
  memory_upsert_entity      — add/update a knowledge graph node
  memory_add_relationship   — add a knowledge graph edge
  memory_get_related        — query edges from an entity

Port: MEMORY_MCP_PORT (default 3030)
DB:   MEMORY_DB_PATH   (default /data/memory.db — use :memory: for tests)

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #708
"""

import os
from pathlib import Path
from typing import Any, Optional

import uvicorn
from mcp.server.fastmcp import Context, FastMCP

from factory_runtime.shared_tenancy import (
    default_project_id,
    header_workspace_id,
    resolve_tenant_identity,
)

from .store import MemoryStore


def _container_data_dir_is_writable() -> bool:
    container_data_dir = Path("/data")
    return container_data_dir.is_dir() and os.access(container_data_dir, os.W_OK)


def resolve_memory_db_path() -> str:
    explicit_path = str(os.getenv("MEMORY_DB_PATH", "")).strip()
    if explicit_path:
        return explicit_path

    instance_id = str(os.getenv("FACTORY_INSTANCE_ID", "default")).strip() or "default"
    factory_data_dir = str(os.getenv("FACTORY_DATA_DIR", "")).strip()
    if factory_data_dir:
        return str(
            Path(factory_data_dir).expanduser() / "memory" / instance_id / "memory.db"
        )

    if _container_data_dir_is_writable():
        return "/data/memory.db"

    repo_root = Path(__file__).resolve().parents[4]
    return str(
        repo_root / ".tmp" / "runtime-data" / "memory" / instance_id / "memory.db"
    )


_db_path = resolve_memory_db_path()
_store = MemoryStore(db_path=_db_path)

mcp = FastMCP("mcp-memory", json_response=True)


def extract_project_id(ctx: Context) -> str:
    """Extract the workspace tenant ID from the HTTP request context.

    Compatibility mode may fall back to ``PROJECT_WORKSPACE_ID`` for the
    per-workspace runtime. Promoted shared mode must receive an explicit tenant
    selector and rejects missing or ambiguous identity.
    """
    headers = None
    if ctx.request_context and hasattr(ctx.request_context, "request"):
        headers = getattr(ctx.request_context.request, "headers", None)
    return resolve_tenant_identity(
        header_project_id=header_workspace_id(headers),
        fallback_project_id=default_project_id(),
    )


# ---------------------------------------------------------------------------
# Lessons (long-term memory)
# ---------------------------------------------------------------------------


@mcp.tool()
def memory_purge_workspace(ctx: Context) -> dict[str, Any]:
    """Admin tool: purge all memory records for the caller's workspace identity."""
    project_id = extract_project_id(ctx)
    counts = _store.purge_workspace(project_id)
    return {"ok": True, "counts": counts}


@mcp.tool()
def memory_store_lesson(
    issue_number: int,
    outcome: str,
    summary: str,
    learnings: list[str],
    ctx: Context,
    repo: str = "",
) -> dict[str, Any]:
    """Store a lesson learned from a completed issue run."""
    lesson_id = _store.store_lesson(
        issue_number=issue_number,
        outcome=outcome,
        summary=summary,
        learnings=learnings,
        repo=repo,
        project_id=extract_project_id(ctx),
    )
    return {"ok": True, "lesson_id": lesson_id}


@mcp.tool()
def memory_get_lessons(issue_number: int, ctx: Context) -> dict[str, Any]:
    """Return all stored lessons for a specific issue number."""
    return {"lessons": _store.get_lessons(issue_number, extract_project_id(ctx))}


@mcp.tool()
def memory_search_similar(query: str, ctx: Context, limit: int = 5) -> dict[str, Any]:
    """Search past lessons by keyword similarity."""
    return {
        "results": _store.search_similar(
            query=query, limit=limit, project_id=extract_project_id(ctx)
        )
    }


@mcp.tool()
def memory_get_recent(ctx: Context, limit: int = 10) -> dict[str, Any]:
    """Return the N most recent lessons across all issues."""
    return {
        "lessons": _store.get_recent_lessons(
            limit=limit, project_id=extract_project_id(ctx)
        )
    }


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


@mcp.tool()
def memory_upsert_entity(
    name: str,
    kind: str,
    ctx: Context,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Add or update a knowledge graph entity node."""
    _store.upsert_entity(
        name=name, kind=kind, metadata=metadata, project_id=extract_project_id(ctx)
    )
    return {"ok": True}


@mcp.tool()
def memory_add_relationship(
    from_entity: str,
    relation: str,
    to_entity: str,
    ctx: Context,
) -> dict[str, Any]:
    """Add a directed edge between two knowledge graph entities."""
    _store.add_relationship(
        from_entity=from_entity,
        relation=relation,
        to_entity=to_entity,
        project_id=extract_project_id(ctx),
    )
    return {"ok": True}


@mcp.tool()
def memory_get_related(
    entity: str,
    ctx: Context,
    relation: Optional[str] = None,
) -> dict[str, Any]:
    """Query outgoing edges from a knowledge graph entity."""
    return {
        "relationships": _store.get_related(
            entity=entity, relation=relation, project_id=extract_project_id(ctx)
        )
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run mcp-memory with Streamable HTTP transport mounted at /mcp."""
    host = os.getenv("MEMORY_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MEMORY_MCP_PORT", "3030"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
