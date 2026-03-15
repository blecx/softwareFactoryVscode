"""Thin HTTP client for talking to the mcp-agent-bus MCP server.

Uses httpx to make JSON-RPC style calls to the bus.
All methods are async.
"""

from __future__ import annotations

import httpx
from typing import Any, Optional


class BusClient:
    """Async HTTP client for the mcp-agent-bus server."""

    def __init__(self, base_url: str = "http://localhost:3031") -> None:
        self._base_url = base_url.rstrip("/")

    async def _call(self, tool: str, args: dict[str, Any]) -> Any:
        """POST a tool call to the bus MCP endpoint and return the result."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._base_url}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "id": 1,
                    "params": {"name": tool, "arguments": args},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # FastMCP returns result in data["result"]["content"][0]["text"]
            result = data.get("result", {})
            content = result.get("content", [])
            if content:
                import json as _json

                raw = content[0].get("text", "{}")
                return _json.loads(raw)
            return result

    async def list_pending(self) -> list[dict[str, Any]]:
        """Return runs awaiting approval."""
        result = await self._call("bus_list_pending_approval", {})
        return result.get("runs", [])

    async def read_context_packet(self, run_id: str) -> dict[str, Any]:
        """Return the full context packet for a run."""
        return await self._call("bus_read_context_packet", {"run_id": run_id})

    async def approve_run(self, run_id: str, feedback: str = "") -> None:
        """Approve a plan."""
        await self._call("bus_approve_run", {"run_id": run_id, "feedback": feedback})

    async def reject_run(self, run_id: str, feedback: str = "") -> None:
        """Reject a plan by transitioning to failed."""
        await self._call("bus_set_status", {"run_id": run_id, "status": "failed"})
