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

See: docs/agents/MAESTRO-DESIGN.md
Implements: GitHub issue #708
"""

import os
from typing import Any, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP

from .store import MemoryStore

_db_path = os.getenv("MEMORY_DB_PATH", "/data/memory.db")
_store = MemoryStore(db_path=_db_path)

mcp = FastMCP("mcp-memory", json_response=True)


# ---------------------------------------------------------------------------
# Lessons (long-term memory)
# ---------------------------------------------------------------------------


@mcp.tool()
def memory_store_lesson(
    issue_number: int,
    outcome: str,
    summary: str,
    learnings: list[str],
    repo: str = "",
) -> dict[str, Any]:
    """Store a lesson learned from a completed issue run.

    Args:
        issue_number: GitHub issue number that was resolved.
        outcome: One of 'success', 'failure', or 'partial'.
        summary: One-paragraph human-readable summary of what happened.
        learnings: List of concrete take-aways to apply to future similar issues.
        repo: GitHub repo slug (owner/repo). Optional.

    Returns:
        {"ok": True, "lesson_id": <int>}
    """
    lesson_id = _store.store_lesson(
        issue_number=issue_number,
        outcome=outcome,
        summary=summary,
        learnings=learnings,
        repo=repo,
    )
    return {"ok": True, "lesson_id": lesson_id}


@mcp.tool()
def memory_get_lessons(issue_number: int) -> dict[str, Any]:
    """Return all stored lessons for a specific issue number.

    Returns:
        {"lessons": [{"id", "issue_number", "outcome", "summary", "learnings", "ts"}, ...]}
    """
    return {"lessons": _store.get_lessons(issue_number)}


@mcp.tool()
def memory_search_similar(query: str, limit: int = 5) -> dict[str, Any]:
    """Search past lessons by keyword similarity.

    Finds lessons whose summary or learnings contain all words in the query.
    Used by RouterAgent to adjust complexity scores based on past outcomes.

    Args:
        query: Free-text search (e.g. issue title or key domain terms).
        limit: Maximum number of results to return (default 5).

    Returns:
        {"results": [{"issue_number", "outcome", "summary", "learnings", "ts"}, ...]}
    """
    return {"results": _store.search_similar(query=query, limit=limit)}


@mcp.tool()
def memory_get_recent(limit: int = 10) -> dict[str, Any]:
    """Return the N most recent lessons across all issues.

    Useful for short-term context: 'what did the agent just do?'

    Returns:
        {"lessons": [...]}
    """
    return {"lessons": _store.get_recent_lessons(limit=limit)}


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


@mcp.tool()
def memory_upsert_entity(
    name: str,
    kind: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Add or update a knowledge graph entity node.

    Args:
        name: Unique identifier (e.g. 'apps/api/services/template_service.py').
        kind: Node type: 'file' | 'domain' | 'service' | 'issue' | 'agent'.
        metadata: Optional JSON dict with extra properties.

    Returns:
        {"ok": True}
    """
    _store.upsert_entity(name=name, kind=kind, metadata=metadata)
    return {"ok": True}


@mcp.tool()
def memory_add_relationship(
    from_entity: str,
    relation: str,
    to_entity: str,
) -> dict[str, Any]:
    """Add a directed edge between two knowledge graph entities.

    Args:
        from_entity: Source entity name.
        relation: Edge type: 'belongs_to' | 'changed_by' | 'depends_on' | 'tested_by'.
        to_entity: Target entity name.

    Returns:
        {"ok": True}
    """
    _store.add_relationship(
        from_entity=from_entity, relation=relation, to_entity=to_entity
    )
    return {"ok": True}


@mcp.tool()
def memory_get_related(
    entity: str,
    relation: Optional[str] = None,
) -> dict[str, Any]:
    """Query outgoing edges from a knowledge graph entity.

    Args:
        entity: Source entity name to query.
        relation: Optional filter (e.g. 'depends_on'). If omitted, returns all edges.

    Returns:
        {"relationships": [{"from_entity", "relation", "to_entity", "ts"}, ...]}
    """
    return {"relationships": _store.get_related(entity=entity, relation=relation)}


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
