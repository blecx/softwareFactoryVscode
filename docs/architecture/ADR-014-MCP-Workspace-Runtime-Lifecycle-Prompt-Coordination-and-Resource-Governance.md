# ADR-014: MCP Workspace Runtime Lifecycle, Prompt Coordination, and Resource Governance

## Status

Proposed

## Context

The repository already has accepted architecture for:

- namespace-first runtime ownership under `.copilot/softwareFactoryVscode/`
- generated per-workspace endpoints and port allocation
- installed / running / active workspace semantics
- cleanup and reconciliation
- hybrid tenancy for shared-capable services
- architecture authority hierarchy

Those ADRs establish the runtime ownership model, but they do not yet define a complete operating model for:

- MCP service inventory as a first-class catalog
- dependency-aware service lifecycle
- prompt-start readiness checks
- in-flight prompt pause/resume when MCP services fail
- workspace-scoped runtime signaling
- idle suspension and expiry-based runtime deletion
- health-driven repair and restart
- image source fallback and upgrade policy
- active-workspace detection via live activity rather than stale timestamps
- resource governance across multiple workspaces

## Verified current findings motivating this ADR

The current codebase already shows the need for a higher-level runtime architecture:

1. MCP endpoints may be configured while the harness behind them is not running.
2. The advertised dev-start path is incomplete:
   - `🚀 Start: Full Stack (Dev)` depends on `🚀 Dev Stack: Supervised`
   - but that dependency is not defined in the current task graph.
3. The current `dev_stack_supervisor.py` is not a real supervisor; it is a placeholder sleep loop and does not repair or recreate MCP services.
4. Current lifecycle verbs are limited to:
   - `start`
   - `stop`
   - `list`
   - `status`
   - `preflight`
   - `activate`
   - `deactivate`
   - `cleanup`
5. Current runtime metadata is not rich enough for:
   - idle/suspend policy
   - expiry/delete policy
   - per-service health state
   - prompt/session coordination
   - repair history
   - image provenance
6. Current Compose manifests rely mainly on `restart: unless-stopped` and socket/liveness checks; they do not express a complete dependency-aware orchestration model.
7. Prompt execution currently has no explicit contract for:
   - ensuring the MCP harness is ready before work starts
   - pausing when MCP services die mid-execution
   - resuming safely after repair/restart
8. Source checkout and generated workspace authority are still too easy to confuse in operator experience, even though the accepted ADRs already distinguish them.

## Relationship to existing ADRs

This ADR extends but does not replace:

- `ADR-007` — generated effective endpoints and port allocation
- `ADR-008` — hybrid tenancy and shared-capable service rules
- `ADR-009` — installed / running / active lifecycle semantics
- `ADR-010` — cleanup and reconciliation semantics
- `ADR-011` — agent-worker remains a liveness placeholder unless changed explicitly
- `ADR-012` — namespaced runtime ownership under `.copilot/softwareFactoryVscode/`
- `ADR-013` — accepted ADRs remain the authoritative architecture source

## Terms

- **MCP harness**: the complete runtime required to serve one workspace safely, including workspace-facing MCP servers and required support/control-plane services.
- **Workspace-facing MCP server**: an MCP service projected into workspace MCP settings and intended for direct workspace tool use.
- **Shared-capable control-plane service**: a service such as `mcp-memory`, `mcp-agent-bus`, or `approval-gate` that may run per-workspace or in deliberate shared mode under `ADR-008`.
- **Activity lease**: a live, renewable indication that a workspace is actively in use by an operator-facing surface.
- **Execution lease**: a live, renewable indication that a prompt/session is actively running or paused-for-repair against a workspace.
- **Suspend**: graceful runtime quiescing after inactivity while preserving fast restartability.
- **Delete-runtime**: expiry-based removal of workspace runtime resources so the next use becomes a cold start, while preserving the installed baseline under `.copilot/softwareFactoryVscode/`.

## Current service catalog

| Logical key | Compose service | Kind | Scope | Suggested profile(s) | Hard dependencies |
| --- | --- | --- | --- | --- | --- |
| `context7` | `context7` | MCP | workspace-scoped | knowledge, optional | `CONTEXT7_API_KEY`, network |
| `bashGateway` | `bash-gateway-mcp` | MCP | workspace-scoped | execution, core | `/target`, factory-data mount, policy path |
| `git` | `git-mcp` | MCP | workspace-scoped | navigation, core | `/target` |
| `search` | `search-mcp` | MCP | workspace-scoped | navigation, core | `/target` |
| `filesystem` | `filesystem-mcp` | MCP | workspace-scoped | navigation, core | `/target` |
| `dockerCompose` | `docker-compose-mcp` | MCP | workspace-scoped | execution, optional | `/target`, factory-data mount, Docker socket |
| `testRunner` | `test-runner-mcp` | MCP | workspace-scoped | execution, optional | `/target`, factory-data mount |
| `offlineDocs` | `offline-docs-mcp` | MCP | workspace-scoped | knowledge, optional | `/target`, factory-data mount |
| `githubOps` | `github-ops-mcp` | MCP | workspace-scoped | collaboration, optional | `/target`, factory-data mount, GitHub token |
| `mcp-memory` | `mcp-memory` | MCP | shared-capable control plane | control-plane, core | memory persistence |
| `mcp-agent-bus` | `mcp-agent-bus` | MCP | shared-capable control plane | control-plane, core | bus persistence |
| `approval-gate` | `approval-gate` | support HTTP service | shared-capable control plane | control-plane, core | `mcp-agent-bus` |
| `agent-worker` | `agent-worker` | support worker | workspace orchestration support | support | workspace mount, `mcp-memory`, `mcp-agent-bus`, `approval-gate` |
| `mock-llm-gateway` | `mock-llm-gateway` | support HTTP service | workspace-scoped test/support infra | support, optional | none |

## Current logical dependency tree

### Control plane

- `mcp-memory`
- `mcp-agent-bus`
- `approval-gate`
  - depends logically on `mcp-agent-bus`

### Workspace navigation/data plane

- `git`
- `search`
- `filesystem`

These are workspace-scoped and depend mainly on the mounted workspace root.

### Execution plane

- `bashGateway`
- `testRunner`
- `dockerCompose`

These depend on workspace mounts and, in some cases, factory-data mounts and Docker socket access.

### Knowledge/collaboration plane

- `context7`
- `offlineDocs`
- `githubOps`

These depend on external secrets, repo mounts, or local indexes depending on service.

### Orchestration/support plane

- `agent-worker`
  - depends logically on `mcp-memory`, `mcp-agent-bus`, and `approval-gate`
- `mock-llm-gateway`
  - optional support/test service

## Decision

### 1. The runtime must maintain a first-class MCP service catalog

- **Rule:** The runtime must expose one machine-readable service catalog as the source of truth for MCP and support services.
- **Rule:** Each service entry must declare:
  - logical name
  - Compose/runtime identity
  - kind (`MCP`, `support HTTP`, `worker`, etc.)
  - tenancy/scope classification
  - health/readiness semantics
  - dependencies
  - required mounts/resources
  - image source policy
  - profile membership
  - whether the service is core, optional, or on-demand
- **Rule:** The generated workspace settings, runtime manifest, lifecycle manager, runtime verifier, and operator diagnostics must derive from that same catalog.
- **Rule:** The service catalog must hide current implementation naming drift where practical and present operators with one consistent vocabulary.

### 2. The runtime must model both workspace state and per-service state

#### Workspace state

A workspace runtime must have explicit aggregate states such as:

- `installed`
- `starting`
- `running`
- `active`
- `idle-grace`
- `suspended`
- `degraded`
- `repairing`
- `cleanup-pending`
- `deleted`

#### Service state

Each service must also have an explicit service-level state such as:

- `defined`
- `image-ready`
- `starting`
- `healthy`
- `degraded`
- `unreachable`
- `blocked-config`
- `blocked-secret`
- `blocked-host`
- `repairing`
- `stopped`
- `deleted`

- **Rule:** Workspace state must not be inferred only from whether some containers exist.
- **Rule:** Service state must not be collapsed into workspace activation state.
- **Rule:** Operator-facing status must expose both aggregate workspace state and per-service state.

### 3. The system must distinguish operator activity from prompt execution

- **Rule:** `active` continues to mean the explicit operator-selected workspace per `ADR-009`.
- **Rule:** This ADR does not redefine `active`; it adds live lease concepts on top of it.
- **Rule:** The system must track two additional live signals:
  - **activity lease** — operator/workspace surface is genuinely in use
  - **execution lease** — at least one prompt/session is actively using or waiting on the workspace runtime
- **Rule:** A stale `last_activated_at` timestamp is not sufficient for suspend/delete decisions.
- **Rule:** A workspace may be operator-active without an executing prompt, and a prompt may hold an execution lease even if the editor window temporarily loses focus.

### 4. Lifecycle verbs must be expanded and formalized

The runtime architecture must support these lifecycle intents:

- `start`
- `stop`
- `suspend`
- `resume`
- `repair`
- `recreate`
- `cleanup`
- `delete-runtime`
- `pull-images`
- `upgrade-images`

#### Semantic definitions

- **start**: create and launch the required workspace runtime or service subset
- **stop**: stop runtime services while preserving restartability and installed baseline
- **suspend**: graceful inactivity-driven quiescing that preserves fast restartability
- **resume**: restore a suspended workspace runtime
- **repair**: targeted health-based recovery without unnecessary full teardown
- **recreate**: recreate selected services or profiles from declared sources
- **cleanup**: explicit operator-driven runtime cleanup per `ADR-010`
- **delete-runtime**: policy-driven expiry cleanup that makes the next use a cold start
- **pull-images**: refresh approved images from configured registries
- **upgrade-images**: transition to newer allowed images according to policy

- **Rule:** A user-facing “pause” intent may exist, but the normative lifecycle term is `suspend`.
- **Rule:** Raw container `pause`/`unpause` must not be the architectural primary mechanism unless proven safe for the affected service class.

### 5. Start, stop, repair, and recreate must follow a dependency graph

- **Rule:** The runtime must maintain a logical dependency graph independent of whether the Compose files remain relatively flat.
- **Rule:** Services must start in dependency order and stop in reverse dependency order where applicable.
- **Rule:** Repair operations must prefer the smallest safe recovery boundary first.

#### Default logical ordering

1. control plane
   - `mcp-memory`
   - `mcp-agent-bus`

2. approval/control coordination
   - `approval-gate`

3. workspace-facing MCP servers
   - `context7`
   - `bashGateway`
   - `git`
   - `search`
   - `filesystem`
   - `dockerCompose`
   - `testRunner`
   - `offlineDocs`
   - `githubOps`

4. orchestration/support
   - `agent-worker`
   - `mock-llm-gateway` when applicable

- **Rule:** Shared-capable control-plane repair must be treated differently from workspace-scoped service repair because it may affect more than one workspace.
- **Rule:** The absence of current explicit Compose `depends_on` must not prevent the lifecycle manager from enforcing dependency-aware orchestration.

### 6. The runtime must support service profiles

- **Rule:** The system must support profile-based runtime start and readiness, not just all-or-nothing full-stack startup.
- **Rule:** The architecture must support at least:
  - `navigation`
  - `execution`
  - `knowledge`
  - `collaboration`
  - `control-plane`
  - `full-factory`
- **Rule:** Prompts and workflows must be able to request the minimal required profile set.
- **Rule:** Profile needs may expand during execution if new tool families become necessary.
- **Rule:** The runtime must support progressive profile expansion rather than assuming every prompt’s full service set is known in advance.
- **Rule:** Prompt readiness may begin with a minimal estimated profile, but the runtime must support progressive profile expansion when new required tool families are discovered during execution.

### 7. Prompt execution must gate on MCP harness readiness before work begins

- **Rule:** Before executing a new prompt that depends on MCP tools, the system must verify that the required MCP harness for the target workspace is ready.
- **Rule:** Readiness must include:
  - correct workspace identity
  - required service profile available
  - required MCP endpoints reachable
  - required dependencies healthy
  - no blocking config drift
  - no blocking secret/config absence for required services
- **Rule:** If readiness fails, the prompt must not proceed blindly.
- **Rule:** The prompt must instead enter `waiting-for-runtime`, trigger allowed ramp-up/repair policy, or fail fast with actionable operator guidance.

### 8. Prompt execution must pause and resume across recoverable runtime interruptions

- **Rule:** If required MCP services die, restart, or become unreachable during prompt execution, the prompt must not be treated as terminally failed by default.
- **Rule:** The system must distinguish:
  - transient interruption
  - recoverable runtime degradation
  - non-recoverable semantic failure
- **Rule:** For transient or recoverable interruption, the prompt must enter `paused-for-runtime-repair`.
- **Rule:** After required services become healthy again, the prompt may resume from the last safe checkpoint.
- **Rule:** If safe resume is impossible, the prompt must fail explicitly with a recovery reason rather than silently replaying work.

#### Prompt/session states

Prompt execution should support states such as:

- `queued`
- `waiting-for-runtime`
- `running`
- `paused-for-runtime-repair`
- `resuming`
- `completed`
- `failed-recoverable`
- `failed-terminal`

### 9. Prompt recovery must be checkpoint-based and idempotency-aware

- **Rule:** Prompt execution must checkpoint at safe boundaries such as tool-call boundaries or equivalent workflow checkpoints.
- **Rule:** Resumption after repair/restart must continue from the last safe checkpoint, not blindly restart the whole prompt.
- **Rule:** Recovery must account for side-effect ambiguity.
- **Rule:** Mutating tool calls should support correlation IDs / operation IDs where feasible so replay safety can be reasoned about.
- **Rule:** The system must distinguish:
  - definitely not executed
  - may have executed
  - definitely executed

### 10. The runtime must emit workspace-scoped signals

- **Rule:** The runtime must expose workspace-scoped signals consumable by:
  - prompt/session execution
  - operator-facing workspace surfaces
  - future runtime controllers or reconcilers
- **Rule:** Signal semantics are architectural; transport is implementation-specific.
- **Rule:** Signals must include at least:
  - `workspace-starting`
  - `workspace-ready`
  - `workspace-degraded`
  - `workspace-suspended`
  - `workspace-delete-pending`
  - `workspace-deleted`
  - `service-starting`
  - `service-healthy`
  - `service-degraded`
  - `service-repairing`
  - `service-restarted`
  - `prompt-paused-runtime`
  - `prompt-resume-allowed`
  - `prompt-restart-required`
  - `prompt-fail-terminal`
- **Rule:** Signals must be scoped to canonical workspace identity, not to accidental source-checkout fallback identity.

### 11. Idle suspend and delete-runtime policy must be lease-aware

- **Rule:** A workspace may transition from `running` to `idle-grace` and then `suspended` after configurable inactivity.
- **Rule:** A workspace may transition from `suspended` or long-term inactive state to `delete-runtime` eligibility after a longer configurable inactivity period.
- **Rule:** An execution lease must block suspend and delete-runtime transitions.
- **Rule:** An activity lease must block suspend and delete-runtime transitions unless an explicit stronger policy says otherwise.
- **Rule:** Shared-capable services must not be deleted merely because one dependent workspace goes inactive.
- **Rule:** Shared-capable control-plane services must use host-level dependency/reference evaluation and must not be suspended or deleted while any dependent workspace still holds a valid activity lease or execution lease.
- **Rule:** Suspend/delete policy for shared-capable services must aggregate dependent-workspace leases and must not evaluate any single workspace in isolation.

#### Policy guidance

- short inactivity grace before suspend: configurable, likely minutes or hours
- long inactivity grace before delete-runtime: configurable; an initial implementation may choose **2 days**
- exact default durations belong in policy/implementation, not this ADR

### 12. Delete-runtime must be a cold-start reset of runtime resources, not of the installed baseline

- **Rule:** `delete-runtime` must remove workspace runtime resources sufficiently for the next use to be a cold start.
- **Rule:** `delete-runtime` must preserve the namespace-first installed baseline under `.copilot/softwareFactoryVscode/`.
- **Rule:** `delete-runtime` must not silently remove the installed factory checkout, the architectural namespace, or host-owned bridge files beyond what existing cleanup rules explicitly allow.
- **Rule:** `delete-runtime` should reuse the cleanup contract from `ADR-010` where applicable, but be triggered by expiry policy rather than explicit operator command.
- **Rule:** Workspace runtime deletion does not imply host-global image pruning.

### 13. Health and repair must be explicit, bounded, and cause-aware

Health evaluation must consider more than “port open”.

A service should be evaluated against:

- container/process existence
- Docker health state where defined
- endpoint reachability
- MCP handshake success where applicable
- dependency readiness
- mount availability
- required secret/config presence
- tenant identity readiness when relevant
- drift against runtime manifest and service catalog

#### Repair ladder

Repairs should escalate in order:

1. re-probe
2. restart service
3. recreate service
4. repair dependency
5. pull/rebuild image
6. reconcile workspace metadata
7. surface terminal operator-visible failure

- **Rule:** Repairs must use bounded retries and backoff.
- **Rule:** The system must avoid infinite restart or prompt replay loops.
- **Rule:** Host-level failures such as Docker daemon outage, network outage, or disk exhaustion must be classified separately from service-level failure.
- **Rule:** The runtime should expose circuit-breaker behavior when repeated repair attempts are failing.
- **Rule:** Prompt pause/resume and runtime repair must use bounded retries, backoff, and circuit-breaker behavior to prevent endless restart loops, endless prompt replay, or silent livelock.

### 14. Image acquisition, trust, and upgrade policy must be first-class

The runtime must support explicit image acquisition policy such as:

1. pinned digest from approved registry
2. tagged image from approved registry
3. local cached image
4. local build from source

- **Rule:** Each service must declare its image policy mode.
- **Rule:** The runtime must record image provenance, version/digest, and acquisition source in runtime metadata.
- **Rule:** Automatic pull/upgrade behavior must be policy-driven and operator-visible.
- **Rule:** Approved registries and source locations must be allowlisted.
- **Rule:** Automatic pull or upgrade must respect workspace safety/approval policy and must not silently widen the trust boundary.
- **Rule:** Automatic image pull, rebuild, or upgrade actions must be governed by the workspace approval/safety profile and must not silently widen the repository’s configured trust boundary.

### 15. The source checkout must not create a second runtime contract

- **Rule:** The generated installed workspace remains the canonical runtime ownership surface.
- **Rule:** Source-checkout tooling may inspect or operate the companion installed workspace only when it resolves to the same canonical identity.
- **Rule:** Wrong-surface operations must fail fast rather than fabricating a new runtime contract.
- **Rule:** Workspace signals, leases, lifecycle, and prompt recovery must all resolve through the canonical installed-workspace identity.

### 16. This ADR does not assign the controller role to the current `agent-worker`

- **Rule:** `ADR-011` remains true for the current implementation: `agent-worker` is presently a liveness placeholder, not a real runtime controller.
- **Rule:** The controller/reconciler required by this ADR may be a different component.
- **Rule:** Acceptance of this ADR must not be interpreted as retroactively changing `agent-worker` semantics without an explicit implementation change.

### 17. The runtime must provide operator-visible diagnostics and auditability

- **Rule:** The runtime must expose enough truth for an operator to understand:
  - what is running
  - what is degraded
  - what was suspended
  - what was deleted
  - what was repaired
  - why a prompt paused, resumed, restarted, or failed
- **Rule:** Runtime decisions such as suspend, delete-runtime, repair, recreate, pull, and upgrade must emit reason codes and timestamps.
- **Rule:** The operator should be able to distinguish:
  - policy-driven lifecycle action
  - health-driven repair action
  - manual operator action
  - prompt-coordination action

## Consequences

### Positive consequences

- MCP runtime behavior becomes explicit and governable.
- Prompts become more resilient to transient runtime failure.
- Resource usage can be reduced for inactive workspaces without sacrificing recoverability.
- Shared-capable control-plane services are handled differently from workspace-scoped services where necessary.
- The system gains a defensible model for cold-start expiry and hot/warm recovery.
- Source-checkout drift becomes easier to reject instead of accidentally tolerated.

### Trade-offs

- The architecture introduces a richer state model and a true runtime coordination layer.
- Prompt execution now depends on checkpointing and replay safety.
- Runtime signaling and lease management must be implemented carefully.
- Policy surface increases: suspend, delete-runtime, repair, pull, upgrade, and profile selection all need explicit operator defaults.

## Non-goals

This ADR does not define:

- the concrete transport used for runtime signaling
- the exact default timeout values
- the exact UI surface in VS Code for all signals
- the specific controller implementation component
- the final service-profile selection algorithm
- the exact checkpoint storage format
- host-global image pruning policy beyond the rule that it remains separate from per-workspace runtime deletion

## Decision summary

The architecture must evolve from “manual container lifecycle plus generated endpoints” to a full workspace MCP runtime operating model with:

- a first-class service catalog
- dependency-aware lifecycle orchestration
- per-service and per-workspace state
- live activity and execution leases
- prompt readiness gating
- pause/resume during runtime repair
- suspend/delete-runtime resource governance
- explicit health/repair logic
- policy-driven image sourcing and upgrade
- canonical workspace-scoped runtime signaling

This ADR also requires profile-aware readiness with progressive expansion, lease-aware shared-service suspend/delete protection, bounded runtime/prompt recovery, and approval-governed image mutation.

This ADR extends the existing accepted ADR set without replacing their authority.
