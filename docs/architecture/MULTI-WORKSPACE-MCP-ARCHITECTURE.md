# Multi-Workspace and Multi-Tenant MCP Architecture

## Status

Maintained synthesis

This document is a maintained architecture synthesis. It is not a replacement for the ADRs.

- Per `ADR-013`, accepted ADRs define architecture guardrails and terminology, while this document explains and synthesizes them.
- Accepted runtime contracts live in `ADR-012`, `ADR-007`, `ADR-008`, `ADR-009`, `ADR-010`, and `ADR-014`.
- Hybrid-tenancy promotion rules now live in accepted `ADR-008`; the current default branch satisfies those rules for `mcp-memory`, `mcp-agent-bus`, and `approval-gate`, while workspace-scoped services remain isolated by default.
- This document explains how those decisions fit together, maps them onto the current codebase, and keeps future-work boundaries explicit.

When this document lags, the accepted ADRs and verified code are authoritative.

## Why this architecture exists

`softwareFactoryVscode` no longer operates as a single-workspace localhost-only runtime.

The repository now supports:

- namespace-first installed workspaces under `.copilot/softwareFactoryVscode/`,
- generated per-workspace host-port maps,
- generated `software-factory.code-workspace` files,
- generated runtime manifests used by verification and lifecycle helpers,
- host-level workspace registry and lifecycle commands,
- and a deliberate path toward selected shared services without weakening workspace isolation by default.

The remaining architecture work is not “invent multi-workspace support from scratch.” It is to keep the current runtime contract coherent, continue hardening the now-fulfilled shared control plane, and preserve workspace isolation for services that remain workspace-scoped by design.

## Core guardrails

### 1. Namespace-first runtime ownership remains canonical

The canonical installed-workspace runtime contract lives under `.copilot/softwareFactoryVscode/`, including:

- `.copilot/softwareFactoryVscode/.factory.env`
- `.copilot/softwareFactoryVscode/lock.json`
- `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`
- workspace-scoped data directories derived from `FACTORY_DATA_DIR`
- the generated host-facing `software-factory.code-workspace` bridge file

Root-level `.factory.env`, `.factory.lock.json`, or hidden-tree `.softwareFactoryVscode/` artifacts must not be reintroduced as canonical ownership surfaces.

### 2. One source of truth drives effective endpoints

The same effective runtime metadata must drive:

- Docker host-port publishing,
- generated MCP URLs in `software-factory.code-workspace`,
- runtime manifest endpoint data,
- lifecycle status/preflight inspection,
- and runtime verification.

This prevents drift between Compose, VS Code, and verifier expectations.

### 3. Source checkout must not create a second runtime contract

The source checkout may operate against the companion installed workspace, but it must resolve to the same:

- target workspace identity,
- compose project,
- port block,
- runtime manifest,
- and generated workspace contract.

Source-checkout `.vscode/settings.json` must not commit a second static MCP URL contract.

### 4. Single-tenant by default, multi-tenant by deliberate promotion

Per `ADR-008`, services that assume one repository root or direct project filesystem state remain workspace-scoped until deliberately redesigned.

`mcp-memory`, `mcp-agent-bus`, and `approval-gate` now satisfy the accepted promotion rules in `ADR-008` for deliberate shared-mode use. That does **not** make shared mode mandatory for every workspace: the practical default path remains the per-workspace runtime unless operators intentionally opt into shared topology.

## Current supported architecture

### 1. Host control plane

The host control plane is implemented through the workspace registry and lifecycle helpers in `scripts/factory_workspace.py` and `scripts/factory_stack.py`.

Current supported concepts:

- `FACTORY_INSTANCE_ID` — unique installed-workspace runtime identity
- `PROJECT_WORKSPACE_ID` — stable logical workspace identifier
- host-scoped registry file — records workspace path, compose project, port block, runtime state, and timestamps
- explicit installed / running / active state separation

Current lifecycle commands:

- `factory_stack.py list`
- `factory_stack.py status`
- `factory_stack.py preflight`
- `factory_stack.py start`
- `factory_stack.py stop`
- `factory_stack.py activate`
- `factory_stack.py deactivate`
- `factory_stack.py cleanup`

### 2. Workspace runtime plane

Each installed workspace owns a runtime envelope rooted in the namespace-first install contract.

The current runtime envelope includes:

- persisted effective port variables in `.copilot/softwareFactoryVscode/.factory.env`
- a generated runtime manifest under `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`
- a generated `software-factory.code-workspace` file at the host project root
- a compose project name and port index stored in both env/manifest/registry surfaces
- workspace-scoped data directories for memory/bus persistence

### 3. Effective endpoint pipeline

Effective runtime endpoints are already generated and persisted.

Today the codebase already:

- allocates distinct workspace port blocks,
- collision-checks the selected block before startup,
- projects concrete MCP URLs into the generated workspace file,
- writes the same endpoint map into the runtime manifest,
- and validates those generated endpoints during preflight/runtime verification.

This is no longer aspirational architecture; it is part of the current runtime contract.

### 4. VS Code workspace plane

The generated `software-factory.code-workspace` file is the supported host-facing entrypoint for installed workspaces.

- `.copilot/config/vscode-agent-settings.json` remains the canonical schema/template source.
- Installed workspaces project concrete URLs from the effective runtime metadata.
- The generated workspace file is a projection of the installed-workspace contract, not the canonical authoring source.

### 5. Service classification

The runtime currently supports two service classes.

#### Workspace-scoped services

These remain one-instance-per-workspace because they depend on a repository mount or direct project filesystem state.

Examples include:

- bash gateway,
- repo fundamentals services,
- docker-compose MCP,
- test runner MCP,
- offline docs,
- GitHub ops.

#### Candidate shared services

These services may eventually be promoted to a shared control-plane role, but that promotion is not automatic.

Current candidate shared services include:

- `mcp-memory`
- `mcp-agent-bus`
- `approval-gate`
- supporting orchestration services that depend on the same control-plane lifecycle

Current code already carries tenant-aware storage/routing groundwork in these services, but that does **not** mean the rollout is complete or approved as a final shared multi-tenant control plane.

### 6. Active workspace semantics

The authoritative architectural definition of `active` lives in `ADR-009`. This section is a synthesis of that rule and the current implementation.

The architecture distinguishes three states:

- **installed** — the namespace-first factory install exists for a target repository
- **running** — Docker runtime resources are currently allocated for that workspace
- **active** — the workspace currently selected by the operator-facing tool context, such as the VS Code workspace or Copilot CLI session, and recorded explicitly in the host registry

Important current behavior:

- more than one workspace may be running at once,
- active is an operator/session concept rather than proof of port ownership,
- in practice, the current implementation records that selection explicitly through `factory_stack.py activate` rather than by automatically detecting editor/window focus,
- `activate` refreshes generated runtime artifacts from the canonical installed-workspace contract and then marks the workspace active,
- switching `A -> B -> A` is treated as a fresh explicit selection each time, so activate/deactivate flows clear stale selection-lease metadata rather than reusing old lease holders or timestamps from a previously active workspace,
- `deactivate` clears active selection without implicitly stopping containers.

### 7. Cleanup and reconciliation semantics

The current runtime supports both reconciliation and explicit cleanup.

- `list` performs registry reconciliation before reporting state.
- `cleanup` removes runtime ownership and generated runtime artifacts for the selected workspace, while leaving the installed `.copilot/softwareFactoryVscode/` baseline in place.
- Generated host-facing bridge files such as `software-factory.code-workspace` remain part of the installed baseline and may be refreshed later.

Broader discovery-time reconciliation hardening is still governed by `ADR-010` and remains an area to keep reviewing.

## What is implemented now vs. what remains future work

### Implemented now

- namespace-first runtime ownership
- host registry with active workspace selection
- generated port blocks and generated workspace MCP URLs
- generated runtime manifest and preflight drift detection
- lifecycle commands for start/stop/status/preflight/activate/deactivate/cleanup
- source-checkout fallback to the companion installed-workspace runtime contract
- throwaway validation reusing the shared lifecycle helper

### Still future or intentionally incomplete

- continuing operational hardening and release communication around the now-fulfilled shared control plane
- strict no-ambiguity tenant enforcement across every shared-service entrypoint
- broader registry rebuild and discovery-time hardening beyond the currently implemented reconciliation paths
- shared-service optimization that reduces per-workspace infrastructure only after isolation proof exists

## Review checkpoints

When reviewing future changes against this architecture, ask:

1. Does the change preserve `.copilot/softwareFactoryVscode/` as the canonical runtime namespace?
2. Does it keep Compose, generated workspace settings, runtime manifest, and verification on the same effective endpoint contract?
3. Does source-checkout tooling still resolve to the companion installed workspace rather than inventing a second runtime identity?
4. Does it preserve installed / running / active as explicit and operator-visible concepts?
5. If a service is being treated as shared, has it satisfied the tenant-isolation promotion rules from `ADR-008`?

## Decision summary

The supported architecture is now:

- multiple installed workspaces,
- multiple concurrently runnable workspace stacks through generated port blocks,
- generated workspace-local MCP URLs and runtime manifests,
- explicit registry-backed lifecycle management,
- workspace-scoped data-plane services by default,
- and a controlled, reviewable path toward shared services only where isolation can be proven.

This keeps the runtime aligned with the accepted ADRs and the verified codebase without overstating future shared-service promotion as already complete.
