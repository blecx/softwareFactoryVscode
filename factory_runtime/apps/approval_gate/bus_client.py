"""Thin HTTP client for talking to the mcp-agent-bus MCP server.

Uses httpx to make JSON-RPC style calls to the bus.
All methods are async.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

DEFAULT_MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SESSION_ID_HEADER = "mcp-session-id"
MCP_PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
MCP_ACCEPT_HEADER = "application/json, text/event-stream"


class BusClientError(RuntimeError):
    """Raised when an MCP call to mcp-agent-bus fails."""


def _decode_result_payload(result: dict[str, Any]) -> Any:
    structured = result.get("structuredContent")
    if structured is not None:
        return structured

    content = result.get("content", [])
    if content:
        raw = content[0].get("text", "{}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    return result


class BusClient:
    """Async HTTP client for the mcp-agent-bus server."""

    def __init__(self, base_url: str = "http://localhost:3031") -> None:
        self._base_url = base_url.rstrip("/")

    def _endpoint_url(self) -> str:
        return f"{self._base_url}/mcp"

    async def _call(
        self, tool: str, args: dict[str, Any], project_id: str = "default"
    ) -> Any:
        """POST a tool call to the bus MCP endpoint and return the result."""
        endpoint_url = self._endpoint_url()
        base_headers = {
            "Content-Type": "application/json",
            MCP_PROTOCOL_VERSION_HEADER: DEFAULT_MCP_PROTOCOL_VERSION,
            "Accept": MCP_ACCEPT_HEADER,
            "X-Workspace-ID": project_id,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                init_resp = await client.post(
                    endpoint_url,
                    headers=base_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": DEFAULT_MCP_PROTOCOL_VERSION,
                            "capabilities": {},
                            "clientInfo": {
                                "name": "approval-gate-bus-client",
                                "version": "1.0",
                            },
                        },
                    },
                )
                init_resp.raise_for_status()

                session_headers = dict(base_headers)
                session_id = init_resp.headers.get(MCP_SESSION_ID_HEADER)
                if session_id:
                    session_headers[MCP_SESSION_ID_HEADER] = session_id

                notify_resp = await client.post(
                    endpoint_url,
                    headers=session_headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    },
                )
                notify_resp.raise_for_status()

                resp = await client.post(
                    endpoint_url,
                    headers=session_headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 2,
                        "params": {"name": tool, "arguments": args},
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise BusClientError(f"HTTP error calling `{tool}`: {exc}") from exc

            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise BusClientError(
                    f"Invalid JSON response calling `{tool}`: {exc}"
                ) from exc

            if "error" in data:
                error = data["error"]
                if isinstance(error, dict):
                    message = str(error.get("message") or error)
                else:
                    message = str(error)
                raise BusClientError(message)

            result = data.get("result", {})
            if isinstance(result, dict):
                payload = _decode_result_payload(result)
                if result.get("isError"):
                    if isinstance(payload, dict):
                        message = json.dumps(payload, sort_keys=True)
                    else:
                        message = str(payload)
                    raise BusClientError(
                        message or f"MCP tool `{tool}` returned an error"
                    )
                return payload

            return result

    async def list_pending(self, project_id: str = "default") -> list[dict[str, Any]]:
        """Return runs awaiting approval."""
        result = await self._call(
            "bus_list_pending_approval", {}, project_id=project_id
        )
        return result.get("runs", [])

    async def read_context_packet(
        self, run_id: str, project_id: str = "default"
    ) -> dict[str, Any]:
        """Return the full context packet for a run."""
        return await self._call(
            "bus_read_context_packet", {"run_id": run_id}, project_id=project_id
        )

    async def approve_run(
        self, run_id: str, feedback: str = "", project_id: str = "default"
    ) -> None:
        """Approve a plan."""
        await self._call(
            "bus_approve_run",
            {"run_id": run_id, "feedback": feedback},
            project_id=project_id,
        )

    async def reject_run(
        self, run_id: str, feedback: str = "", project_id: str = "default"
    ) -> None:
        """Reject a plan by transitioning to failed."""
        await self._call(
            "bus_set_status",
            {"run_id": run_id, "status": "failed"},
            project_id=project_id,
        )
