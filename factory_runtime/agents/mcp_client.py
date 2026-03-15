"""MCPMultiClient — unified async client routing tool calls across N MCP servers.

Connects to N FastMCP servers simultaneously, merges their tool manifests
into one namespace, and routes call_tool(name, args) to the correct server.

Protocol: MCP Streamable HTTP (JSON-RPC 2.0) over POST /mcp

Used by all FACTORY agents (router, coder, orchestrator) to access:
  - mcp-memory   (:3030)  — knowledge graph and lessons
  - mcp-agent-bus(:3031)  — task run context bus
  - mcp-bash-gateway (:3011) — shell execution (in Docker worker)
  - mcp-github-ops (:3018) — PR creation

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #711
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


class ToolNotFoundError(KeyError):
    """Raised when a requested tool is not registered on any connected server."""


class ToolConflictError(ValueError):
    """Raised when two servers expose a tool with the same name."""


class MCPCallError(RuntimeError):
    """Raised when an MCP tool call returns a JSON-RPC error or HTTP error."""


@dataclass
class ToolInfo:
    """Metadata for one MCP tool from the merged manifest."""

    name: str
    description: str
    server_name: str
    server_url: str
    input_schema: dict[str, Any] = field(default_factory=dict)


class MCPMultiClient:
    """Connects to N FastMCP servers, merges their tool manifests, and routes calls.

    Usage::

        async with MCPMultiClient([
            {"name": "memory", "url": "http://localhost:3030"},
            {"name": "bus",    "url": "http://localhost:3031"},
        ]) as client:
            tools = client.list_tools()
            result = await client.call_tool("memory_store_lesson", {...})
    """

    def __init__(
        self,
        servers: list[dict[str, str]],
        timeout: float = 10.0,
    ) -> None:
        """
        Args:
            servers: List of {"name": str, "url": str} dicts.
            timeout: HTTP timeout in seconds for each request.
        """
        self._servers = servers
        self._timeout = timeout
        self._tools: dict[str, ToolInfo] = {}
        self._http: Optional[httpx.AsyncClient] = None
        self._req_id = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MCPMultiClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open HTTP sessions to all servers and fetch tool manifests."""
        self._http = httpx.AsyncClient(timeout=self._timeout)
        self._tools = {}

        for server in self._servers:
            name = server["name"]
            url = server["url"].rstrip("/")
            tools = await self._fetch_tools(url, name)
            for tool in tools:
                if tool.name in self._tools:
                    existing = self._tools[tool.name]
                    raise ToolConflictError(
                        f"Tool '{tool.name}' is exposed by both "
                        f"'{existing.server_name}' ({existing.server_url}) and "
                        f"'{name}' ({url}). Rename one of the tools."
                    )
                self._tools[tool.name] = tool

    async def close(self) -> None:
        """Close all HTTP sessions."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Tool manifest
    # ------------------------------------------------------------------

    def list_tools(self) -> list[ToolInfo]:
        """Return all tools from all connected servers (merged manifest)."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolInfo:
        """Return metadata for a specific tool. Raises ToolNotFoundError if unknown."""
        if name not in self._tools:
            raise ToolNotFoundError(
                f"Tool '{name}' not found. Available: {sorted(self._tools.keys())}"
            )
        return self._tools[name]

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def call_tool(self, name: str, args: Optional[dict[str, Any]] = None) -> Any:
        """Call a tool by name with the provided arguments.

        Routes the call to the correct server based on the merged manifest.

        Args:
            name: Tool name (must exist in the merged manifest).
            args: Tool arguments dict. Pass None or {} for tools with no parameters.

        Returns:
            Parsed JSON result from the tool.

        Raises:
            ToolNotFoundError: Tool doesn't exist on any connected server.
            MCPCallError: The server returned an error or HTTP failure.
        """
        tool = self.get_tool(name)  # raises ToolNotFoundError if missing
        return await self._rpc_call(
            tool.server_url,
            "tools/call",
            {
                "name": name,
                "arguments": args or {},
            },
        )

    # ------------------------------------------------------------------
    # Internal JSON-RPC helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _rpc_call(
        self, base_url: str, method: str, params: dict[str, Any]
    ) -> Any:
        """Send a JSON-RPC 2.0 request to the MCP endpoint and return the result."""
        assert (
            self._http is not None
        ), "Call connect() or use async context manager first"

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        try:
            resp = await self._http.post(
                f"{base_url}/mcp",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MCPCallError(
                f"HTTP error calling {base_url}/mcp ({method}): {exc}"
            ) from exc

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise MCPCallError(f"Invalid JSON response from {base_url}: {exc}") from exc

        if "error" in data:
            err = data["error"]
            raise MCPCallError(
                f"MCP error from {base_url} tool call: [{err.get('code')}] {err.get('message')}"
            )

        return data.get("result")

    async def _fetch_tools(self, base_url: str, server_name: str) -> list[ToolInfo]:
        """Fetch tool manifest from one server via tools/list RPC."""
        result = await self._rpc_call(base_url, "tools/list", {})
        tools_raw = result.get("tools", []) if isinstance(result, dict) else []

        tools = []
        for t in tools_raw:
            tools.append(
                ToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    server_name=server_name,
                    server_url=base_url,
                    input_schema=t.get("inputSchema", {}),
                )
            )
        return tools
