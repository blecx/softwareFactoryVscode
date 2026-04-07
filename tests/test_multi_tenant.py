import os
import pytest
from factory_runtime.apps.mcp.agent_bus.bus import AgentBus
from factory_runtime.apps.mcp.memory.store import MemoryStore


def test_agent_bus_multi_tenant_isolation():
    """Test that two different workspaces inside AgentBus cannot see each other's data and are perfectly isolated."""
    # Use memory database for isolated testing
    bus = AgentBus(db_path=":memory:")

    # Tenant 1 adds a run
    run1 = bus.create_run(issue_number=101, repo="org/tenant1", project_id="tenant-1")
    
    # Tenant 2 adds a run
    run2 = bus.create_run(issue_number=202, repo="org/tenant2", project_id="tenant-2")

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
    
    # Write a plan requires only run_id, since run_id identifies the task uniquely
    bus.write_plan(run1, goal="tenant 1 goal", files=[])
    bus.write_plan(run2, goal="tenant 2 goal", files=[])
    
    # Check purge counts
    counts = bus.purge_workspace(project_id="tenant-1")
    assert counts["runs"] == 1
    assert counts["plans"] == 1
    
    # Tenant 1 run is gone
    assert bus.get_run(run1, project_id="tenant-1") is None
    
    # Tenant 2 run is safe
    assert bus.get_run(run2, project_id="tenant-2") is not None


def test_memory_store_multi_tenant_isolation():
    """Test that MemoryStore perfectly isolates data via project_id."""
    store = MemoryStore(db_path=":memory:")
    
    # Tenant 1 saves a lesson
    store.store_lesson(
        issue_number=1, outcome="success", summary="T1 summary", learnings=["did something"], project_id="tenant-A"
    )
    
    # Tenant 2 saves a lesson
    store.store_lesson(
        issue_number=2, outcome="success", summary="T2 summary", learnings=["another thing"], project_id="tenant-B"
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

