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

DEFAULT_MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SESSION_ID_HEADER = "mcp-session-id"
MCP_PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
MCP_ACCEPT_HEADER = "application/json, text/event-stream"


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


@dataclass
class ServerSession:
    """Per-server MCP session metadata."""

    server_name: str
    server_url: str
    endpoint_url: str
    session_id: str | None = None
    initialized: bool = False


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
        protocol_version: str = DEFAULT_MCP_PROTOCOL_VERSION,
        transport: httpx.AsyncBaseTransport | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """
        Args:
            servers: List of {"name": str, "url": str} dicts.
            timeout: HTTP timeout in seconds for each request.
        """
        self._servers = servers
        self._timeout = timeout
        self._protocol_version = protocol_version
        self._transport = transport
        self._workspace_id = workspace_id
        self._tools: dict[str, ToolInfo] = {}
        self._sessions: dict[str, ServerSession] = {}
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
        self._http = httpx.AsyncClient(timeout=self._timeout, transport=self._transport)
        self._tools = {}
        self._sessions = {}

        for server in self._servers:
            name = server["name"]
            url = server["url"].rstrip("/")
            session = await self._initialize_server(name, url)
            tools = await self._fetch_tools(session)
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
        self._sessions = {}

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

    def get_all_tool_definitions(self) -> list[dict[str, Any]]:
        """Return all tools formatted for OpenAI-compatible tool calling."""
        definitions: list[dict[str, Any]] = []
        for tool in self.list_tools():
            parameters = tool.input_schema
            if not isinstance(parameters, dict) or not parameters:
                parameters = {"type": "object", "properties": {}}
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                }
            )
        return definitions

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
        session = self._sessions.get(tool.server_url)
        if session is None or not session.initialized:
            session = await self._initialize_server(tool.server_name, tool.server_url)
        return await self._rpc_call(
            session,
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

    def _normalize_endpoint_url(self, base_url: str) -> str:
        """Return the MCP endpoint URL for one server base URL."""
        normalized = base_url.rstrip("/")
        if normalized.endswith("/mcp"):
            return normalized
        return f"{normalized}/mcp"

    def _build_headers(
        self,
        *,
        session_id: str | None = None,
        include_accept: bool = True,
    ) -> dict[str, str]:
        """Build required Streamable HTTP headers."""
        headers = {
            "Content-Type": "application/json",
            MCP_PROTOCOL_VERSION_HEADER: self._protocol_version,
        }
        if include_accept:
            headers["Accept"] = MCP_ACCEPT_HEADER
        if session_id:
            headers[MCP_SESSION_ID_HEADER] = session_id
        if self._workspace_id:
            headers["X-Workspace-ID"] = self._workspace_id
        return headers

    async def _initialize_server(
        self, server_name: str, base_url: str
    ) -> ServerSession:
        """Perform the MCP initialize handshake for one server."""
        existing = self._sessions.get(base_url)
        if existing is not None and existing.initialized:
            return existing

        session = ServerSession(
            server_name=server_name,
            server_url=base_url,
            endpoint_url=self._normalize_endpoint_url(base_url),
        )

        result, response = await self._rpc_request(
            session.endpoint_url,
            payload={
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "software-factory-mcp-client",
                        "version": "1.0",
                    },
                },
            },
            headers=self._build_headers(),
        )
        _ = result
        session.session_id = response.headers.get(MCP_SESSION_ID_HEADER)

        await self._rpc_notify(
            session.endpoint_url,
            payload={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            headers=self._build_headers(session_id=session.session_id),
        )

        session.initialized = True
        self._sessions[base_url] = session
        return session

    async def _rpc_notify(
        self,
        endpoint_url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        """Send a JSON-RPC notification to the MCP endpoint."""
        assert (
            self._http is not None
        ), "Call connect() or use async context manager first"

        try:
            resp = await self._http.post(endpoint_url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MCPCallError(
                f"HTTP error calling {endpoint_url} ({payload.get('method')}): {exc}"
            ) from exc

    async def _rpc_call(
        self, session: ServerSession, method: str, params: dict[str, Any]
    ) -> Any:
        """Send a JSON-RPC 2.0 request to the MCP endpoint and return the result."""
        result, _ = await self._rpc_request(
            session.endpoint_url,
            payload={
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params,
            },
            headers=self._build_headers(session_id=session.session_id),
        )
        return result

    async def _rpc_request(
        self,
        endpoint_url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> tuple[Any, httpx.Response]:
        """Send a JSON-RPC 2.0 request to the MCP endpoint and return result+response."""
        assert (
            self._http is not None
        ), "Call connect() or use async context manager first"

        try:
            resp = await self._http.post(endpoint_url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MCPCallError(
                f"HTTP error calling {endpoint_url} ({payload.get('method')}): {exc}"
            ) from exc

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise MCPCallError(
                f"Invalid JSON response from {endpoint_url}: {exc}"
            ) from exc

        if "error" in data:
            err = data["error"]
            raise MCPCallError(
                f"MCP error from {endpoint_url} tool call: [{err.get('code')}] {err.get('message')}"
            )

        return data.get("result"), resp

    async def _fetch_tools(self, session: ServerSession) -> list[ToolInfo]:
        """Fetch tool manifest from one server via tools/list RPC."""
        result = await self._rpc_call(session, "tools/list", {})
        tools_raw = result.get("tools", []) if isinstance(result, dict) else []

        tools = []
        for t in tools_raw:
            tools.append(
                ToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    server_name=session.server_name,
                    server_url=session.server_url,
                    input_schema=t.get("inputSchema", {}),
                )
            )
        return tools
