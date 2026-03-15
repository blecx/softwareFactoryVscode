"""FastMCP server for mcp-agent-bus.

Exposes AgentBus through 8 MCP tools:
  bus_create_run          — start a new task run
  bus_write_plan          — store the implementation plan
  bus_approve_run         — human approves the plan
  bus_read_context_packet — read all run state in one call (core primitive)
  bus_write_snapshot      — record before/after for one file
  bus_write_validation    — record one validation command result
  bus_write_checkpoint    — record a named milestone
  bus_set_status          — transition run status

Port: AGENT_BUS_PORT (default 3031)
DB:   AGENT_BUS_DB_PATH  (default /data/agent_bus.db — use :memory: for tests)

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #710
"""

import os
from typing import Any, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP

from .bus import AgentBus, InvalidStatusTransitionError

_db_path = os.getenv("AGENT_BUS_DB_PATH", "/data/agent_bus.db")
_bus = AgentBus(db_path=_db_path)

mcp = FastMCP("mcp-agent-bus", json_response=True)


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_create_run(issue_number: int, repo: str = "") -> dict[str, Any]:
    """Create a new agent task run for a GitHub issue.

    Args:
        issue_number: GitHub issue number to work on.
        repo: GitHub repo slug (e.g. 'owner/repo'). Optional.

    Returns:
        {"run_id": str}  — UUID identifying this run throughout its lifecycle.
    """
    run_id = _bus.create_run(issue_number=issue_number, repo=repo)
    return {"run_id": run_id}


@mcp.tool()
def bus_set_status(run_id: str, status: str) -> dict[str, Any]:
    """Transition a run to a new status.

    Valid lifecycle: created → routing → planning → awaiting_approval →
                     approved → coding → validating → reviewing →
                     pr_created → done. Any state → failed.

    Args:
        run_id: Run UUID returned by bus_create_run.
        status: Target status string.

    Returns:
        {"ok": True} on success.
    """
    try:
        _bus.set_status(run_id=run_id, status=status)
    except InvalidStatusTransitionError as exc:
        raise ValueError(str(exc)) from exc
    return {"ok": True}


@mcp.tool()
def bus_list_pending_approval() -> dict[str, Any]:
    """Return all runs currently awaiting human approval.

    Returns:
        {"runs": [{"run_id", "issue_number", "repo", "status", "created_ts"}, ...]}
    """
    return {"runs": _bus.list_pending_approval()}


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_write_plan(
    run_id: str,
    goal: str,
    files: list[str],
    acceptance_criteria: list[str],
    validation_cmds: list[str],
    estimated_minutes: Optional[int] = None,
) -> dict[str, Any]:
    """Write (or replace) the implementation plan for a run.

    Should be called after the agent has generated a plan and the run
    status has been moved to 'planning'. The presence of a plan
    automatically enables the human approval gate.

    Args:
        run_id: Run UUID.
        goal: One-sentence description of what will be implemented.
        files: List of file paths that will be modified.
        acceptance_criteria: Ordered list of testable acceptance criteria.
        validation_cmds: Shell commands to run to validate the implementation.
        estimated_minutes: Agent's estimate of implementation time. Optional.

    Returns:
        {"ok": True}
    """
    _bus.write_plan(
        run_id=run_id,
        goal=goal,
        files=files,
        acceptance_criteria=acceptance_criteria,
        validation_cmds=validation_cmds,
        estimated_minutes=estimated_minutes,
    )
    return {"ok": True}


@mcp.tool()
def bus_approve_run(run_id: str, feedback: str = "") -> dict[str, Any]:
    """Mark a plan as approved by a human reviewer.

    Transitions the run from 'awaiting_approval' → 'approved'.
    Called by the Approval Gate server when the user confirms.

    Args:
        run_id: Run UUID.
        feedback: Optional reviewer comment to pass to the coder agent.

    Returns:
        {"ok": True}
    """
    try:
        _bus.approve_run(run_id=run_id, feedback=feedback)
    except InvalidStatusTransitionError as exc:
        raise ValueError(str(exc)) from exc
    return {"ok": True}


# ---------------------------------------------------------------------------
# Context packet
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_read_context_packet(run_id: str) -> dict[str, Any]:
    """Read the full context packet for a run in one call.

    This is the core FACTORY primitive. Any agent calls this once
    to get the complete run state: issue metadata, approved plan,
    every file snapshot, and recent validation results.

    No context is lost between agent phases because all state
    lives here rather than in agent message threads.

    Args:
        run_id: Run UUID.

    Returns:
        {
          "run": {"run_id", "issue_number", "repo", "status", ...},
          "plan": {"goal", "files", "acceptance_criteria", ...} | null,
          "file_snapshots": [{"filepath", "content_before", "content_after", "ts"}, ...],
          "validation_results": [...],  // last 3 validation results
          "checkpoints": [{"label", "metadata", "ts"}, ...]
        }
    """
    return _bus.read_context_packet(run_id=run_id)


# ---------------------------------------------------------------------------
# File snapshots
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_write_snapshot(
    run_id: str,
    filepath: str,
    content_before: Optional[str],
    content_after: Optional[str],
) -> dict[str, Any]:
    """Record before/after content for a file modified during a run.

    Called by CoderAgent after every file edit. Enables full diff
    reconstruction and rollback if needed.

    Args:
        run_id: Run UUID.
        filepath: Workspace-relative file path (e.g. 'apps/api/services/x.py').
        content_before: Original file content, or null for new files.
        content_after: Modified file content, or null for deleted files.

    Returns:
        {"ok": True}
    """
    _bus.write_snapshot(
        run_id=run_id,
        filepath=filepath,
        content_before=content_before,
        content_after=content_after,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_write_validation(
    run_id: str,
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    passed: bool,
) -> dict[str, Any]:
    """Record the result of a validation command (test/lint run).

    Called by CoderAgent after each pytest/flake8/npm run.
    Enables RouterAgent and Orchestrator to see validation history.

    Args:
        run_id: Run UUID.
        command: The shell command that was run (e.g. 'pytest tests/unit/').
        stdout: Captured standard output.
        stderr: Captured standard error.
        exit_code: Process exit code (0 = success).
        passed: True if validation passed (exit_code == 0 and no failures).

    Returns:
        {"ok": True}
    """
    _bus.write_validation(
        run_id=run_id,
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        passed=passed,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_write_checkpoint(
    run_id: str,
    label: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record a named milestone checkpoint within a run.

    Provides fine-grained audit trail and enables resumability.
    Standard labels: 'plan_generated', 'coding_complete', 'validation_passed'.

    Args:
        run_id: Run UUID.
        label: Human-readable milestone name.
        metadata: Optional JSON dict with extra context.

    Returns:
        {"ok": True}
    """
    _bus.write_checkpoint(run_id=run_id, label=label, metadata=metadata)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run mcp-agent-bus with Streamable HTTP transport mounted at /mcp."""
    host = os.getenv("AGENT_BUS_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_BUS_PORT", "3031"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# Dynamic Key Injection
# ---------------------------------------------------------------------------


@mcp.tool()
def bus_set_live_key(api_key: str) -> dict[str, Any]:
    """Set a live OpenAI API key dynamically to override mock endpoints.

    Args:
        api_key: The real API key to use.
    """
    import os

    override_path = os.getenv("LLM_OVERRIDE_PATH", "configs/runtime_override.json")
    os.makedirs(os.path.dirname(override_path), exist_ok=True)
    import json

    with open(override_path, "w") as f:
        json.dump({"api_key": api_key}, f)
    return {"ok": True, "message": "Live key updated dynamically."}
