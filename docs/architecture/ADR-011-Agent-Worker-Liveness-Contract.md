# ADR-011: Agent-Worker Liveness Contract (Option A)

**Status:** Accepted  
**Date:** 2025-01-01  
**Context:** Production readiness review identified `agent-worker` container as a non-functional sleep loop placeholder.

---

## Context

The `agent-worker` Docker service (`docker/agent-worker/Dockerfile`) runs `factory_runtime.agents.factory_cli run-queue`, which calls `_run_queue_loop()` in `factory_cli.py`.

That function is **explicitly Option A**: a liveness placeholder loop. It does not consume a real work queue. It logs a heartbeat message every 5 seconds and runs indefinitely:

```python
def _run_queue_loop(poll_interval_seconds: float = 5.0) -> int:
    """Run a placeholder liveness loop for containerized agent-worker mode.

    Option A: Liveness placeholder — keeps the container alive for future
    queue integration without consuming real work items.
    """
    while True:
        time.sleep(poll_interval_seconds)
```

## Decision

This is an **intentional architectural choice** for the VS Code-native factory runtime:

- The VS Code runtime model uses **Copilot Chat agents** (e.g., `@queue-backend`, `@queue-phase-2`) as the orchestration layer, not a background worker container consuming a queue.
- `agent-worker` is retained as a container stub so the install manifest includes it (liveness check, port allocation), but it does not implement work consumption.
- Real agent execution happens through Copilot Chat → MCP tool mesh (approval-gate, mcp-agent-bus, bash-gateway-mcp, etc.).

## Consequences

- `agent-worker` will restart-loop only if the process exits abnormally; the sleep loop means it stays alive satisfying `restart: unless-stopped`.
- Future queue integration (Option B: wire a real Redis/filesystem queue) would replace `_run_queue_loop()` without changing the container manifest or Dockerfile.
- This container intentionally has **no healthcheck** — it has no listening port to probe. A liveness probe via process existence is sufficient for Docker's `unless-stopped` restart policy.

## Related

- `factory_runtime/agents/factory_cli.py` — `_run_queue_loop()` implementation
- `docker/agent-worker/Dockerfile` — container definition
- `docs/WORK-ISSUE-WORKFLOW.md` — canonical workflow using Copilot Chat agents
