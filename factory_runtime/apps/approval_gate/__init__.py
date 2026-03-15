"""Approval Gate — human-in-the-loop FastAPI server for FACTORY plan review.

Endpoints:
  GET  /health                  — liveness probe
  GET  /pending                 — list runs awaiting approval
  GET  /plan/{run_id}           — full plan card for one run
  POST /approve/{run_id}        — approve or reject a plan
  WS   /ws/approvals            — push stream of new pending plans

The gate talks to mcp-agent-bus via HTTP calls (AGENT_BUS_URL env var).
It is stateless — all state lives in the bus.

Port: APPROVAL_GATE_PORT (default 8001)
Bus:  AGENT_BUS_URL      (default http://localhost:3031)

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #718
"""
