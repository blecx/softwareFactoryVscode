import asyncio
import json
from pathlib import Path

import httpx
import pytest

from factory_runtime.apps.approval_gate import main as approval_gate_main
from factory_runtime.apps.mcp.agent_bus import mcp_server as agent_bus_mcp_server
from factory_runtime.apps.mcp.agent_bus.bus import AgentBus
from factory_runtime.apps.mcp.memory import mcp_server as memory_mcp_server
from factory_runtime.apps.mcp.memory.store import MemoryStore
from factory_runtime.shared_tenancy import TenantIdentityError


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

    websocket = _FakeWebSocket(
        headers={"X-Workspace-ID": "tenant-a"},
        query_params={"project_id": "tenant-b"},
    )

    with pytest.raises(TenantIdentityError, match="Tenant identity mismatch"):
        approval_gate_main.websocket_project_id(websocket)


def test_agent_bus_server_resolves_db_path_from_factory_data_dir(monkeypatch):
    monkeypatch.delenv("AGENT_BUS_DB_PATH", raising=False)
    monkeypatch.setenv("FACTORY_DATA_DIR", "/tmp/factory-data")
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-7")

    assert agent_bus_mcp_server.resolve_agent_bus_db_path() == (
        "/tmp/factory-data/bus/workspace-7/agent_bus.db"
    )


def test_agent_bus_server_falls_back_to_repo_tmp_db_path(monkeypatch):
    monkeypatch.delenv("AGENT_BUS_DB_PATH", raising=False)
    monkeypatch.delenv("FACTORY_DATA_DIR", raising=False)
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-8")
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

    assert memory_mcp_server.resolve_memory_db_path() == (
        "/tmp/factory-data/memory/workspace-7/memory.db"
    )


def test_memory_server_falls_back_to_repo_tmp_db_path(monkeypatch):
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    monkeypatch.delenv("FACTORY_DATA_DIR", raising=False)
    monkeypatch.setenv("FACTORY_INSTANCE_ID", "workspace-8")
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
