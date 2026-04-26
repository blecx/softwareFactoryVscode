import asyncio
import json
from pathlib import Path

import httpx
import pytest

from factory_runtime.apps.mcp import sqlite_permissions
from factory_runtime.apps.mcp.agent_bus.bus import AgentBus
from factory_runtime.apps.mcp.memory.store import MemoryStore
from factory_runtime.shared_tenancy import TenantIdentityError


def _approval_gate_main():
    pytest.importorskip("fastapi")
    from factory_runtime.apps.approval_gate import main as approval_gate_main

    return approval_gate_main


def _memory_mcp_server():
    pytest.importorskip("mcp.server.fastmcp")
    from factory_runtime.apps.mcp.memory import mcp_server as memory_mcp_server

    return memory_mcp_server


def _agent_bus_mcp_server():
    pytest.importorskip("mcp.server.fastmcp")
    from factory_runtime.apps.mcp.agent_bus import mcp_server as agent_bus_mcp_server

    return agent_bus_mcp_server


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class _FakeRequestContext:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.request = _FakeRequest(headers=headers)


class _FakeMCPContext:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.request_context = (
            _FakeRequestContext(headers=headers) if headers is not None else None
        )


class _FakeWebSocket:
    def __init__(
        self,
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> None:
        self.headers = headers or {}
        self.query_params = query_params or {}


class _ApprovalGateBusAdapter:
    def __init__(self, bus: AgentBus) -> None:
        self._bus = bus

    async def list_pending(
        self, project_id: str = "default"
    ) -> list[dict[str, object]]:
        return self._bus.list_pending_approval(project_id=project_id)

    async def read_context_packet(
        self, run_id: str, project_id: str = "default"
    ) -> dict[str, object]:
        return self._bus.read_context_packet(run_id, project_id=project_id)

    async def approve_run(
        self, run_id: str, feedback: str = "", project_id: str = "default"
    ) -> None:
        self._bus.approve_run(run_id, feedback=feedback, project_id=project_id)

    async def reject_run(
        self, run_id: str, feedback: str = "", project_id: str = "default"
    ) -> None:
        _ = feedback
        self._bus.set_status(run_id, "failed", project_id=project_id)


def _seed_pending_run(
    bus: AgentBus,
    *,
    issue_number: int,
    repo: str,
    project_id: str,
    goal: str,
) -> str:
    run_id = bus.create_run(
        issue_number=issue_number,
        repo=repo,
        project_id=project_id,
    )
    bus.set_status(run_id, "routing", project_id=project_id)
    bus.set_status(run_id, "planning", project_id=project_id)
    bus.write_plan(
        run_id,
        goal=goal,
        files=["src/example.py"],
        acceptance_criteria=["criterion"],
        validation_cmds=["pytest tests/test_multi_tenant.py"],
        project_id=project_id,
    )
    bus.set_status(run_id, "awaiting_approval", project_id=project_id)
    return run_id


def _patch_bus_client_transport(
    monkeypatch, transport: httpx.AsyncBaseTransport
) -> None:
    from factory_runtime.apps.approval_gate import (
        bus_client as approval_gate_bus_client,
    )

    real_async_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(
        approval_gate_bus_client.httpx,
        "AsyncClient",
        _client_factory,
    )


def _mock_bus_transport(tools_call_payload: dict[str, object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")

        if method == "initialize":
            return httpx.Response(
                200,
                headers={"mcp-session-id": "session-1"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "serverInfo": {"name": "mock-bus", "version": "1.0"},
                    },
                },
            )

        if method == "notifications/initialized":
            return httpx.Response(202, text="")

        if method == "tools/call":
            return httpx.Response(200, json=tools_call_payload)

        raise AssertionError(f"Unexpected MCP method: {method}")

    return httpx.MockTransport(handler)


def _initialize_mcp_server(base_url: str, fastmcp_server) -> httpx.Response:
    fastmcp_server._session_manager = None
    app = fastmcp_server.streamable_http_app()
    session_manager = fastmcp_server._session_manager
    assert session_manager is not None

    async def run() -> httpx.Response:
        async with session_manager.run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=base_url,
            ) as client:
                return await client.post(
                    "/mcp",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                        "mcp-protocol-version": "2025-03-26",
                        "X-Workspace-ID": "tenant-A",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "tenant-proof-tests",
                                "version": "1.0",
                            },
                        },
                    },
                )

    return asyncio.run(run())


def test_agent_bus_multi_tenant_isolation():
    """Test that two different workspaces inside AgentBus cannot see each other's data and are perfectly isolated."""
    # Use memory database for isolated testing
    bus = AgentBus(db_path=":memory:")
    try:
        # Tenant 1 adds a run
        run1 = bus.create_run(
            issue_number=101,
            repo="org/tenant1",
            project_id="tenant-1",
        )

        # Tenant 2 adds a run
        run2 = bus.create_run(
            issue_number=202,
            repo="org/tenant2",
            project_id="tenant-2",
        )

        # Both are created
        assert run1 != run2

        run1_data = bus.get_run(run1, project_id="tenant-1")
        assert run1_data is not None
        assert run1_data["issue_number"] == 101

        # Tenant 2 cannot see Tenant 1's run
        run1_data_from_tenant2 = bus.get_run(run1, project_id="tenant-2")
        assert run1_data_from_tenant2 is None

        # List pending tasks for tenant 1
        pending_t1 = bus.list_pending_approval(project_id="tenant-1")
        assert pending_t1 == []

        # Write a plan requires only run_id, since run_id identifies the task uniquely
        bus.write_plan(
            run1,
            goal="tenant 1 goal",
            files=[],
            acceptance_criteria=[],
            validation_cmds=[],
            project_id="tenant-1",
        )
        bus.write_plan(
            run2,
            goal="tenant 2 goal",
            files=[],
            acceptance_criteria=[],
            validation_cmds=[],
            project_id="tenant-2",
        )

        # Check purge counts
        counts = bus.purge_workspace(project_id="tenant-1")
        assert counts["runs"] == 1
        assert counts["plans"] == 1

        # Tenant 1 run is gone
        assert bus.get_run(run1, project_id="tenant-1") is None

        # Tenant 2 run is safe
        assert bus.get_run(run2, project_id="tenant-2") is not None
    finally:
        bus.close()


def test_agent_bus_creates_parent_directory_for_file_backed_database(tmp_path):
    db_path = tmp_path / "nested" / "agent_bus.db"

    bus = AgentBus(db_path=str(db_path))
    try:
        run_id = bus.create_run(
            issue_number=505,
            repo="org/tenant5",
            project_id="tenant-5",
        )

        assert db_path.exists()
        assert bus.get_run(run_id, project_id="tenant-5") is not None
    finally:
        bus.close()


def test_shared_service_extractors_allow_compatibility_fallback(monkeypatch):
    monkeypatch.delenv("FACTORY_TENANCY_MODE", raising=False)
    monkeypatch.setenv("PROJECT_WORKSPACE_ID", "compat-workspace")

    approval_gate_main = _approval_gate_main()
    memory_mcp_server = _memory_mcp_server()
    agent_bus_mcp_server = _agent_bus_mcp_server()
    ctx = _FakeMCPContext()
    request = _FakeRequest()
    websocket = _FakeWebSocket()

    assert memory_mcp_server.extract_project_id(ctx) == "compat-workspace"
    assert agent_bus_mcp_server.extract_project_id(ctx) == "compat-workspace"
    assert approval_gate_main.request_project_id(request) == "compat-workspace"
    assert approval_gate_main.websocket_project_id(websocket) == "compat-workspace"


def test_shared_service_extractors_require_explicit_identity_in_shared_mode(
    monkeypatch,
):
    monkeypatch.setenv("FACTORY_TENANCY_MODE", "shared")
    monkeypatch.setenv("PROJECT_WORKSPACE_ID", "compat-workspace")

    approval_gate_main = _approval_gate_main()
    memory_mcp_server = _memory_mcp_server()
    agent_bus_mcp_server = _agent_bus_mcp_server()
    ctx = _FakeMCPContext()
    request = _FakeRequest()
    websocket = _FakeWebSocket()

    with pytest.raises(TenantIdentityError, match="requires an explicit tenant"):
        memory_mcp_server.extract_project_id(ctx)

    with pytest.raises(TenantIdentityError, match="requires an explicit tenant"):
        agent_bus_mcp_server.extract_project_id(ctx)

    with pytest.raises(TenantIdentityError, match="requires an explicit tenant"):
        approval_gate_main.request_project_id(request)

    with pytest.raises(TenantIdentityError, match="requires an explicit tenant"):
        approval_gate_main.websocket_project_id(websocket)


def test_shared_service_extractors_accept_explicit_identity_in_shared_mode(
    monkeypatch,
):
    monkeypatch.setenv("FACTORY_TENANCY_MODE", "shared")
    monkeypatch.setenv("PROJECT_WORKSPACE_ID", "compat-workspace")

    approval_gate_main = _approval_gate_main()
    memory_mcp_server = _memory_mcp_server()
    agent_bus_mcp_server = _agent_bus_mcp_server()
    ctx = _FakeMCPContext(headers={"X-Workspace-ID": "tenant-7"})
    request = _FakeRequest(headers={"X-Workspace-ID": "tenant-7"})
    websocket = _FakeWebSocket(query_params={"project_id": "tenant-7"})

    assert memory_mcp_server.extract_project_id(ctx) == "tenant-7"
    assert agent_bus_mcp_server.extract_project_id(ctx) == "tenant-7"
    assert approval_gate_main.request_project_id(request) == "tenant-7"
    assert approval_gate_main.websocket_project_id(websocket) == "tenant-7"


def test_shared_service_extractors_reject_mismatched_explicit_selectors(
    monkeypatch,
):
    monkeypatch.setenv("FACTORY_TENANCY_MODE", "shared")
    approval_gate_main = _approval_gate_main()

    websocket = _FakeWebSocket(
        headers={"X-Workspace-ID": "tenant-a"},
        query_params={"project_id": "tenant-b"},
    )

    with pytest.raises(TenantIdentityError, match="Tenant identity mismatch"):
        approval_gate_main.websocket_project_id(websocket)


def test_memory_mcp_server_keeps_lessons_tenant_scoped_at_tool_boundary(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FACTORY_TENANCY_MODE", "shared")
    monkeypatch.setenv("PROJECT_WORKSPACE_ID", "compat-workspace")

    memory_mcp_server = _memory_mcp_server()
    store = MemoryStore(db_path=":memory:")
    monkeypatch.setattr(memory_mcp_server, "_store", store)

    try:
        tenant_a_ctx = _FakeMCPContext(headers={"X-Workspace-ID": "tenant-A"})
        tenant_b_ctx = _FakeMCPContext(headers={"X-Workspace-ID": "tenant-B"})

        memory_mcp_server.memory_store_lesson(
            issue_number=701,
            outcome="success",
            summary="Tenant A lesson",
            learnings=["tenant A learning"],
            ctx=tenant_a_ctx,
            repo="org/tenant-a",
        )
        memory_mcp_server.memory_store_lesson(
            issue_number=702,
            outcome="success",
            summary="Tenant B lesson",
            learnings=["tenant B learning"],
            ctx=tenant_b_ctx,
            repo="org/tenant-b",
        )

        lessons_a = memory_mcp_server.memory_get_recent(ctx=tenant_a_ctx, limit=10)[
            "lessons"
        ]
        lessons_b = memory_mcp_server.memory_get_recent(ctx=tenant_b_ctx, limit=10)[
            "lessons"
        ]

        assert [lesson["summary"] for lesson in lessons_a] == ["Tenant A lesson"]
        assert [lesson["summary"] for lesson in lessons_b] == ["Tenant B lesson"]
    finally:
        store.close()


def test_agent_bus_mcp_server_keeps_pending_and_plan_cards_tenant_scoped(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FACTORY_TENANCY_MODE", "shared")
    monkeypatch.setenv("PROJECT_WORKSPACE_ID", "compat-workspace")

    agent_bus_mcp_server = _agent_bus_mcp_server()
    bus = AgentBus(db_path=":memory:")
    monkeypatch.setattr(agent_bus_mcp_server, "_bus", bus)

    try:
        tenant_a_ctx = _FakeMCPContext(headers={"X-Workspace-ID": "tenant-A"})
        tenant_b_ctx = _FakeMCPContext(headers={"X-Workspace-ID": "tenant-B"})

        run_a = _seed_pending_run(
            bus,
            issue_number=801,
            repo="org/tenant-a",
            project_id="tenant-A",
            goal="Tenant A plan",
        )
        run_b = _seed_pending_run(
            bus,
            issue_number=802,
            repo="org/tenant-b",
            project_id="tenant-B",
            goal="Tenant B plan",
        )

        pending_a = agent_bus_mcp_server.bus_list_pending_approval(ctx=tenant_a_ctx)[
            "runs"
        ]
        pending_b = agent_bus_mcp_server.bus_list_pending_approval(ctx=tenant_b_ctx)[
            "runs"
        ]

        assert [run["run_id"] for run in pending_a] == [run_a]
        assert [run["run_id"] for run in pending_b] == [run_b]

        packet_a = agent_bus_mcp_server.bus_read_context_packet(
            run_a,
            ctx=tenant_a_ctx,
        )

        assert packet_a["run"]["run_id"] == run_a
        assert packet_a["plan"]["goal"] == "Tenant A plan"

        with pytest.raises(ValueError, match="Run not found for project"):
            agent_bus_mcp_server.bus_read_context_packet(run_a, ctx=tenant_b_ctx)

        with pytest.raises(ValueError, match="Run not found for project"):
            agent_bus_mcp_server.bus_approve_run(run_a, ctx=tenant_b_ctx)
    finally:
        bus.close()


def test_agent_bus_mcp_server_accepts_internal_service_host_header() -> None:
    agent_bus_mcp_server = _agent_bus_mcp_server()

    response = _initialize_mcp_server(
        "http://mcp-agent-bus:3031",
        agent_bus_mcp_server.mcp,
    )

    assert response.status_code == 200
    assert response.headers["mcp-session-id"]


def test_memory_mcp_server_accepts_internal_service_host_header() -> None:
    memory_mcp_server = _memory_mcp_server()

    response = _initialize_mcp_server(
        "http://mcp-memory:3030",
        memory_mcp_server.mcp,
    )

    assert response.status_code == 200
    assert response.headers["mcp-session-id"]


def test_approval_gate_bus_client_prefers_structured_content(monkeypatch) -> None:
    from factory_runtime.apps.approval_gate import (
        bus_client as approval_gate_bus_client,
    )

    transport = _mock_bus_transport(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "structuredContent": {
                    "runs": [
                        {
                            "run_id": "run-1",
                            "issue_number": 901,
                            "repo": "org/tenant-a",
                            "created_ts": "2026-01-01T00:00:00Z",
                        }
                    ]
                }
            },
        }
    )
    _patch_bus_client_transport(monkeypatch, transport)

    client = approval_gate_bus_client.BusClient(base_url="http://agent-bus")

    assert asyncio.run(client.list_pending(project_id="tenant-A")) == [
        {
            "run_id": "run-1",
            "issue_number": 901,
            "repo": "org/tenant-a",
            "created_ts": "2026-01-01T00:00:00Z",
        }
    ]


def test_approval_gate_bus_client_raises_for_mcp_tool_error_payload(
    monkeypatch,
) -> None:
    from factory_runtime.apps.approval_gate import (
        bus_client as approval_gate_bus_client,
    )

    transport = _mock_bus_transport(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Run not found for project. Confirm the tenant identity matches the target run.",
                    }
                ],
                "isError": True,
            },
        }
    )
    _patch_bus_client_transport(monkeypatch, transport)

    client = approval_gate_bus_client.BusClient(base_url="http://agent-bus")

    with pytest.raises(
        approval_gate_bus_client.BusClientError,
        match="Run not found for project",
    ):
        asyncio.run(client.read_context_packet("run-1", project_id="tenant-B"))


def test_approval_gate_routes_keep_pending_plan_and_decisions_tenant_scoped(
    monkeypatch,
) -> None:
    pytest.importorskip("fastapi")

    approval_gate_main = _approval_gate_main()

    monkeypatch.setenv("FACTORY_TENANCY_MODE", "shared")
    monkeypatch.setenv("PROJECT_WORKSPACE_ID", "compat-workspace")

    bus = AgentBus(db_path=":memory:")
    monkeypatch.setattr(
        approval_gate_main,
        "_bus",
        _ApprovalGateBusAdapter(bus),
    )

    try:
        run_a = _seed_pending_run(
            bus,
            issue_number=1001,
            repo="org/tenant-a",
            project_id="tenant-A",
            goal="Tenant A pending plan",
        )
        run_b = _seed_pending_run(
            bus,
            issue_number=1002,
            repo="org/tenant-b",
            project_id="tenant-B",
            goal="Tenant B pending plan",
        )

        async def run_test() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=approval_gate_main.app),
                base_url="http://approval-gate",
            ) as client:
                pending_a = await client.get(
                    "/pending",
                    headers={"X-Workspace-ID": "tenant-A"},
                )
                pending_b = await client.get(
                    "/pending",
                    headers={"X-Workspace-ID": "tenant-B"},
                )

                assert pending_a.status_code == 200
                assert pending_b.status_code == 200
                assert [run["run_id"] for run in pending_a.json()] == [run_a]
                assert [run["run_id"] for run in pending_b.json()] == [run_b]

                plan_a = await client.get(
                    f"/plan/{run_a}",
                    headers={"X-Workspace-ID": "tenant-A"},
                )
                wrong_plan = await client.get(
                    f"/plan/{run_a}",
                    headers={"X-Workspace-ID": "tenant-B"},
                )

                assert plan_a.status_code == 200
                assert plan_a.json()["goal"] == "Tenant A pending plan"
                assert wrong_plan.status_code == 404
                assert "Run not found for project" in wrong_plan.json()["detail"]

                wrong_approve = await client.post(
                    f"/approve/{run_a}",
                    headers={"X-Workspace-ID": "tenant-B"},
                    json={"approved": True, "feedback": "wrong tenant"},
                )
                wrong_reject = await client.post(
                    f"/approve/{run_b}",
                    headers={"X-Workspace-ID": "tenant-A"},
                    json={"approved": False, "feedback": "wrong tenant"},
                )

                assert wrong_approve.status_code == 400
                assert wrong_reject.status_code == 400
                assert "Run not found for project" in wrong_approve.json()["detail"]
                assert "Run not found for project" in wrong_reject.json()["detail"]

                approve_a = await client.post(
                    f"/approve/{run_a}",
                    headers={"X-Workspace-ID": "tenant-A"},
                    json={"approved": True, "feedback": "looks good"},
                )
                reject_b = await client.post(
                    f"/approve/{run_b}",
                    headers={"X-Workspace-ID": "tenant-B"},
                    json={"approved": False, "feedback": "needs work"},
                )

                assert approve_a.status_code == 200
                assert reject_b.status_code == 200

        asyncio.run(run_test())
        assert bus.get_run(run_a, project_id="tenant-A")["status"] == "approved"
        assert bus.get_run(run_b, project_id="tenant-B")["status"] == "failed"
    finally:
        bus.close()


def test_agent_bus_server_resolves_db_path_from_factory_data_dir(monkeypatch):
    monkeypatch.delenv("AGENT_BUS_DB_PATH", raising=False)
    monkeypatch.setenv("FACTORY_DATA_DIR", "/tmp/factory-data")
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-7")
    agent_bus_mcp_server = _agent_bus_mcp_server()

    assert agent_bus_mcp_server.resolve_agent_bus_db_path() == (
        "/tmp/factory-data/bus/workspace-7/agent_bus.db"
    )


def test_agent_bus_server_falls_back_to_repo_tmp_db_path(monkeypatch):
    monkeypatch.delenv("AGENT_BUS_DB_PATH", raising=False)
    monkeypatch.delenv("FACTORY_DATA_DIR", raising=False)
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-8")
    agent_bus_mcp_server = _agent_bus_mcp_server()
    monkeypatch.setattr(
        agent_bus_mcp_server,
        "_container_data_dir_is_writable",
        lambda: False,
    )

    expected = (
        Path(agent_bus_mcp_server.__file__).resolve().parents[4]
        / ".tmp"
        / "runtime-data"
        / "bus"
        / "workspace-8"
        / "agent_bus.db"
    )

    assert Path(agent_bus_mcp_server.resolve_agent_bus_db_path()) == expected


def test_memory_server_resolves_db_path_from_factory_data_dir(monkeypatch):
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    monkeypatch.setenv("FACTORY_DATA_DIR", "/tmp/factory-data")
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-7")
    memory_mcp_server = _memory_mcp_server()

    assert memory_mcp_server.resolve_memory_db_path() == (
        "/tmp/factory-data/memory/workspace-7/memory.db"
    )


def test_memory_server_falls_back_to_repo_tmp_db_path(monkeypatch):
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    monkeypatch.delenv("FACTORY_DATA_DIR", raising=False)
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-8")
    memory_mcp_server = _memory_mcp_server()
    monkeypatch.setattr(
        memory_mcp_server,
        "_container_data_dir_is_writable",
        lambda: False,
    )

    expected = (
        Path(memory_mcp_server.__file__).resolve().parents[4]
        / ".tmp"
        / "runtime-data"
        / "memory"
        / "workspace-8"
        / "memory.db"
    )

    assert Path(memory_mcp_server.resolve_memory_db_path()) == expected


def test_mcp_multi_client_forwards_workspace_identity_header():
    from factory_runtime.agents.mcp_client import MCPMultiClient

    observed_headers: list[tuple[str, str | None]] = []
    session_id = "session-tenant"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        observed_headers.append((method, request.headers.get("x-workspace-id")))

        if method == "initialize":
            return httpx.Response(
                200,
                headers={"mcp-session-id": session_id},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "serverInfo": {"name": "mock", "version": "1.0"},
                    },
                },
            )

        if method == "notifications/initialized":
            return httpx.Response(202, text="")

        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "ping_tool",
                                "description": "Ping",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )

        if method == "tools/call":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"ok": True},
                },
            )

        return httpx.Response(404, text="unexpected")

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with MCPMultiClient(
            [{"name": "mock", "url": "http://test-server"}],
            transport=transport,
            workspace_id="tenant-42",
        ) as client:
            assert [tool.name for tool in client.list_tools()] == ["ping_tool"]
            assert await client.call_tool("ping_tool", {"value": "pong"}) == {
                "ok": True
            }

    asyncio.run(run_test())

    assert observed_headers == [
        ("initialize", "tenant-42"),
        ("notifications/initialized", "tenant-42"),
        ("tools/list", "tenant-42"),
        ("tools/call", "tenant-42"),
    ]


def test_memory_store_multi_tenant_isolation():
    """Test that MemoryStore perfectly isolates data via project_id."""
    store = MemoryStore(db_path=":memory:")
    try:
        # Tenant 1 saves a lesson
        store.store_lesson(
            issue_number=1,
            outcome="success",
            summary="T1 summary",
            learnings=["did something"],
            project_id="tenant-A",
        )

        # Tenant 2 saves a lesson
        store.store_lesson(
            issue_number=2,
            outcome="success",
            summary="T2 summary",
            learnings=["another thing"],
            project_id="tenant-B",
        )

        t1_lessons = store.get_recent_lessons(limit=10, project_id="tenant-A")
        assert len(t1_lessons) == 1
        assert t1_lessons[0]["summary"] == "T1 summary"

        t2_lessons = store.get_recent_lessons(limit=10, project_id="tenant-B")
        assert len(t2_lessons) == 1
        assert t2_lessons[0]["summary"] == "T2 summary"

        # Now try to purge tenant A
        counts = store.purge_workspace(project_id="tenant-A")
        assert counts["lessons"] == 1

        assert len(store.get_recent_lessons(limit=10, project_id="tenant-A")) == 0
        assert len(store.get_recent_lessons(limit=10, project_id="tenant-B")) == 1
    finally:
        store.close()


def test_memory_store_creates_parent_directory_for_file_backed_database(tmp_path):
    db_path = tmp_path / "nested" / "memory.db"

    store = MemoryStore(db_path=str(db_path))
    try:
        store.store_lesson(
            issue_number=6,
            outcome="success",
            summary="Stored with auto-created parent dir",
            learnings=["defensive sqlite path handling"],
            project_id="tenant-6",
        )

        assert db_path.exists()
        assert len(store.get_recent_lessons(limit=10, project_id="tenant-6")) == 1
    finally:
        store.close()


def test_memory_store_realigns_sqlite_bind_mount_to_host_uid_gid(
    tmp_path: Path,
    monkeypatch,
):
    db_path = tmp_path / "nested" / "memory.db"
    observed_calls: list[tuple[str, Path, int, int] | tuple[str, Path, int]] = []

    def _record_chown(path, uid, gid):
        observed_calls.append(("chown", Path(path), uid, gid))

    def _record_chmod(path, mode):
        observed_calls.append(("chmod", Path(path), mode))

    monkeypatch.setenv("FACTORY_HOST_UID", "1234")
    monkeypatch.setenv("FACTORY_HOST_GID", "5678")
    monkeypatch.setattr(sqlite_permissions.os, "chown", _record_chown)
    monkeypatch.setattr(sqlite_permissions.os, "chmod", _record_chmod)

    store = MemoryStore(db_path=str(db_path))
    try:
        store.store_lesson(
            issue_number=7,
            outcome="success",
            summary="Host UID/GID remains writable",
            learnings=["sqlite bind mounts are realigned for backup/restore"],
            project_id="tenant-7",
        )
    finally:
        store.close()

    assert ("chown", db_path.parent, 1234, 5678) in observed_calls
    assert (
        "chmod",
        db_path.parent,
        sqlite_permissions.DIRECTORY_MODE,
    ) in observed_calls
    assert ("chown", db_path, 1234, 5678) in observed_calls
    assert ("chmod", db_path, sqlite_permissions.FILE_MODE) in observed_calls


def test_agent_bus_realigns_sqlite_bind_mount_to_host_uid_gid(
    tmp_path: Path,
    monkeypatch,
):
    db_path = tmp_path / "nested" / "agent_bus.db"
    observed_calls: list[tuple[str, Path, int, int] | tuple[str, Path, int]] = []

    def _record_chown(path, uid, gid):
        observed_calls.append(("chown", Path(path), uid, gid))

    def _record_chmod(path, mode):
        observed_calls.append(("chmod", Path(path), mode))

    monkeypatch.setenv("FACTORY_HOST_UID", "2468")
    monkeypatch.setenv("FACTORY_HOST_GID", "1357")
    monkeypatch.setattr(sqlite_permissions.os, "chown", _record_chown)
    monkeypatch.setattr(sqlite_permissions.os, "chmod", _record_chmod)

    bus = AgentBus(db_path=str(db_path))
    try:
        run_id = bus.create_run(
            issue_number=11,
            repo="blecx/softwareFactoryVscode",
            project_id="tenant-11",
        )
        assert run_id
    finally:
        bus.close()

    assert ("chown", db_path.parent, 2468, 1357) in observed_calls
    assert (
        "chmod",
        db_path.parent,
        sqlite_permissions.DIRECTORY_MODE,
    ) in observed_calls
    assert ("chown", db_path, 2468, 1357) in observed_calls
    assert ("chmod", db_path, sqlite_permissions.FILE_MODE) in observed_calls


def test_memory_store_partitions_relationships_and_audit_by_tenant():
    """Relationship storage and mutation audit must remain tenant-partitioned."""
    store = MemoryStore(db_path=":memory:")
    try:
        for tenant in ("tenant-A", "tenant-B"):
            store.add_relationship(
                from_entity="service:memory",
                relation="depends_on",
                to_entity="sqlite",
                project_id=tenant,
            )

        tenant_a_relationships = store.get_related(
            "service:memory",
            relation="depends_on",
            project_id="tenant-A",
        )
        tenant_b_relationships = store.get_related(
            "service:memory",
            relation="depends_on",
            project_id="tenant-B",
        )

        assert len(tenant_a_relationships) == 1
        assert len(tenant_b_relationships) == 1
        assert all(row["project_id"] == "tenant-A" for row in tenant_a_relationships)
        assert all(row["project_id"] == "tenant-B" for row in tenant_b_relationships)

        tenant_a_audit = store.get_audit_log(project_id="tenant-A")
        tenant_b_audit = store.get_audit_log(project_id="tenant-B")

        assert tenant_a_audit[0]["action"] == "add_relationship"
        assert tenant_b_audit[0]["action"] == "add_relationship"
        assert all(event["project_id"] == "tenant-A" for event in tenant_a_audit)
        assert all(event["project_id"] == "tenant-B" for event in tenant_b_audit)

        counts = store.purge_workspace(project_id="tenant-A")

        assert counts["relationships"] == 1
        assert counts["audit_events"] == 1
        assert (
            store.get_related(
                "service:memory",
                relation="depends_on",
                project_id="tenant-A",
            )
            == []
        )
        assert (
            len(
                store.get_related(
                    "service:memory",
                    relation="depends_on",
                    project_id="tenant-B",
                )
            )
            == 1
        )

        post_purge_audit = store.get_audit_log(project_id="tenant-A")
        assert len(post_purge_audit) == 1
        assert post_purge_audit[0]["action"] == "purge_workspace"
    finally:
        store.close()


def test_agent_bus_context_packet_preserves_non_default_project_scope():
    """Context packets must return tenant-scoped plan, snapshot, validation, and checkpoint data."""
    bus = AgentBus(db_path=":memory:")
    try:
        run_id = bus.create_run(
            issue_number=303,
            repo="org/tenant3",
            project_id="tenant-3",
        )
        bus.write_plan(
            run_id,
            goal="tenant 3 goal",
            files=["src/example.py"],
            acceptance_criteria=["criterion"],
            validation_cmds=["pytest tests/test_example.py"],
            project_id="tenant-3",
        )
        bus.write_snapshot(
            run_id,
            filepath="src/example.py",
            content_before="before",
            content_after="after",
            project_id="tenant-3",
        )
        bus.write_validation(
            run_id,
            command="pytest tests/test_example.py",
            stdout="ok",
            stderr="",
            exit_code=0,
            passed=True,
            project_id="tenant-3",
        )
        bus.write_checkpoint(
            run_id,
            label="plan_generated",
            metadata={"files_count": 1},
            project_id="tenant-3",
        )

        packet = bus.read_context_packet(run_id, project_id="tenant-3")

        assert packet["run"]["run_id"] == run_id
        assert packet["plan"]["goal"] == "tenant 3 goal"
        assert packet["file_snapshots"][0]["filepath"] == "src/example.py"
        assert (
            packet["validation_results"][0]["command"] == "pytest tests/test_example.py"
        )
        assert packet["checkpoints"][0]["label"] == "plan_generated"

        with pytest.raises(ValueError):
            bus.read_context_packet(run_id, project_id="tenant-4")
    finally:
        bus.close()


def test_agent_bus_partitions_child_rows_and_audit_by_tenant():
    """Every persisted child row and audit record must carry tenant identity."""
    bus = AgentBus(db_path=":memory:")
    try:
        run_a = bus.create_run(
            issue_number=501,
            repo="org/tenant-a",
            project_id="tenant-A",
        )
        run_b = bus.create_run(
            issue_number=502,
            repo="org/tenant-b",
            project_id="tenant-B",
        )

        for run_id, tenant in ((run_a, "tenant-A"), (run_b, "tenant-B")):
            bus.write_plan(
                run_id,
                goal=f"goal for {tenant}",
                files=["src/example.py"],
                acceptance_criteria=["criterion"],
                validation_cmds=["pytest tests/test_multi_tenant.py"],
                project_id=tenant,
            )
            bus.write_snapshot(
                run_id,
                filepath="src/example.py",
                content_before="before",
                content_after="after",
                project_id=tenant,
            )
            bus.write_validation(
                run_id,
                command="pytest tests/test_multi_tenant.py",
                stdout="ok",
                stderr="",
                exit_code=0,
                passed=True,
                project_id=tenant,
            )
            bus.write_checkpoint(
                run_id,
                label="validation_passed",
                metadata={"tenant": tenant},
                project_id=tenant,
            )

        packet = bus.read_context_packet(run_a, project_id="tenant-A")
        assert packet["plan"]["project_id"] == "tenant-A"
        assert packet["file_snapshots"][0]["project_id"] == "tenant-A"
        assert packet["validation_results"][0]["project_id"] == "tenant-A"
        assert packet["checkpoints"][0]["project_id"] == "tenant-A"

        tenant_a_audit = bus.get_audit_log(project_id="tenant-A", run_id=run_a)
        tenant_b_audit = bus.get_audit_log(project_id="tenant-B", run_id=run_b)

        assert {event["action"] for event in tenant_a_audit} >= {
            "create_run",
            "write_plan",
            "write_snapshot",
            "write_validation",
            "write_checkpoint",
        }
        assert all(event["project_id"] == "tenant-A" for event in tenant_a_audit)
        assert all(event["project_id"] == "tenant-B" for event in tenant_b_audit)

        counts = bus.purge_workspace(project_id="tenant-A")
        assert counts["runs"] == 1
        assert counts["plans"] == 1
        assert counts["snapshots"] == 1
        assert counts["validations"] == 1
        assert counts["checkpoints"] == 1
        assert counts["audit_events"] >= 5

        assert bus.get_run(run_a, project_id="tenant-A") is None
        assert bus.get_run(run_b, project_id="tenant-B") is not None
        assert bus.get_plan(run_b, project_id="tenant-B") is not None

        post_purge_audit = bus.get_audit_log(project_id="tenant-A")
        assert len(post_purge_audit) == 1
        assert post_purge_audit[0]["action"] == "purge_workspace"
    finally:
        bus.close()


def test_partitioned_purge_rejects_blank_project_identity():
    """Blank tenant selectors should never be accepted for destructive purge helpers."""
    store = MemoryStore(db_path=":memory:")
    bus = AgentBus(db_path=":memory:")
    try:
        with pytest.raises(ValueError, match="project_id"):
            store.purge_workspace("")

        with pytest.raises(ValueError, match="project_id"):
            bus.purge_workspace("   ")
    finally:
        store.close()
        bus.close()


def test_agent_bus_rejects_cross_tenant_snapshot_and_checkpoint_writes():
    """Tenant-scoped writes must not succeed against another workspace's run."""
    bus = AgentBus(db_path=":memory:")
    try:
        run_id = bus.create_run(
            issue_number=404,
            repo="org/tenant4",
            project_id="tenant-4",
        )

        with pytest.raises(ValueError):
            bus.write_snapshot(
                run_id,
                filepath="src/example.py",
                content_before="before",
                content_after="after",
                project_id="tenant-5",
            )

        with pytest.raises(ValueError):
            bus.write_checkpoint(
                run_id,
                label="coding_complete",
                metadata={"files_changed": ["src/example.py"]},
                project_id="tenant-5",
            )
    finally:
        bus.close()
