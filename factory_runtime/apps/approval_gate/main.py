"""Approval Gate FastAPI application.

Runs on APPROVAL_GATE_PORT (default 8001).
Talks to mcp-agent-bus at AGENT_BUS_URL (default http://localhost:3031).

Usage:
    uvicorn apps.approval_gate.main:app --port 8001

Or directly (runs uvicorn internally):
    python -m apps.approval_gate.main
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .bus_client import BusClient
from .plan_card import ApprovalRequest, PendingRun, PlanCard

app = FastAPI(title="FACTORY Approval Gate", version="1.0.0")

_bus = BusClient(base_url=os.getenv("AGENT_BUS_URL", "http://localhost:3031"))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "approval-gate"}


# ---------------------------------------------------------------------------
# Pending runs
# ---------------------------------------------------------------------------


@app.get("/pending", response_model=list[PendingRun])
async def get_pending(request: Request) -> list[dict[str, Any]]:
    project_id = request.headers.get("X-Workspace-ID", "default")
    """Return all runs currently awaiting human approval."""
    runs = await _bus.list_pending(project_id=project_id)
    return [
        {
            "run_id": r["run_id"],
            "issue_number": r["issue_number"],
            "repo": r.get("repo", ""),
            "created_ts": r.get("created_ts", ""),
        }
        for r in runs
    ]


# ---------------------------------------------------------------------------
# Plan card
# ---------------------------------------------------------------------------


@app.get("/plan/{run_id}", response_model=PlanCard)
async def get_plan(run_id: str, request: Request) -> dict[str, Any]:
    project_id = request.headers.get("X-Workspace-ID", "default")
    """Return the full plan card for a run awaiting approval."""
    try:
        packet = await _bus.read_context_packet(run_id, project_id=project_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    run = packet.get("run", {})
    plan = packet.get("plan") or {}
    checkpoints = [c["label"] for c in packet.get("checkpoints", [])]

    return {
        "run_id": run_id,
        "issue_number": run.get("issue_number", 0),
        "repo": run.get("repo", ""),
        "status": run.get("status", ""),
        "goal": plan.get("goal", ""),
        "files": plan.get("files", []),
        "acceptance_criteria": plan.get("acceptance_criteria", []),
        "validation_cmds": plan.get("validation_cmds", []),
        "estimated_minutes": plan.get("estimated_minutes"),
        "checkpoints": checkpoints,
    }


# ---------------------------------------------------------------------------
# Approve / reject
# ---------------------------------------------------------------------------


@app.post("/approve/{run_id}")
async def approve(
    run_id: str, body: ApprovalRequest, request: Request
) -> dict[str, Any]:
    project_id = request.headers.get("X-Workspace-ID", "default")
    """Approve or reject a plan.

    - ``approved=true``  → transitions run to 'approved' so CoderAgent continues
    - ``approved=false`` → transitions run to 'failed'
    """
    try:
        if body.approved:
            await _bus.approve_run(
                run_id=run_id, feedback=body.feedback, project_id=project_id
            )
            return {"ok": True, "run_id": run_id, "decision": "approved"}
        else:
            await _bus.reject_run(
                run_id=run_id, feedback=body.feedback, project_id=project_id
            )
            return {"ok": True, "run_id": run_id, "decision": "rejected"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# WebSocket push — new pending plans
# ---------------------------------------------------------------------------


@app.websocket("/ws/approvals")
async def ws_approvals(websocket: WebSocket) -> None:
    project_id = websocket.query_params.get("project_id", "default")
    """Push new pending plans to connected clients.

    Polls mcp-agent-bus every 5 seconds and pushes any runs that are
    in 'awaiting_approval' status. Clients receive JSON objects:
        {"event": "pending", "runs": [...]}
    """
    await websocket.accept()
    seen: set[str] = set()
    try:
        while True:
            runs = await _bus.list_pending(project_id=project_id)
            new_runs = [r for r in runs if r["run_id"] not in seen]
            if new_runs:
                for r in new_runs:
                    seen.add(r["run_id"])
                await websocket.send_text(
                    json.dumps({"event": "pending", "runs": new_runs})
                )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    host = os.getenv("APPROVAL_GATE_HOST", "0.0.0.0")
    port = int(os.getenv("APPROVAL_GATE_PORT", "8001"))
    uvicorn.run("apps.approval_gate.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
