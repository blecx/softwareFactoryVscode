import os

import pytest

from factory_runtime.apps.mcp.agent_bus.bus import AgentBus
from factory_runtime.apps.mcp.memory.store import MemoryStore


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
