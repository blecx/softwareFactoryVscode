# Multi-Workspace and Multi-Tenant MCP Architecture

## Status

Proposed

## Problem Statement

`softwareFactoryVscode` currently assumes a mostly single-workspace localhost runtime model:

- MCP Docker services publish to well-known default host ports.
- `.copilot/config/vscode-agent-settings.json` points to fixed localhost URLs.
- several MCP services assume a single repository mounted at `/target`.
- runtime verification probes default host ports directly.

This works well for one active workspace, but it breaks down when an operator needs to:

- keep several projects installed on the same host,
- run more than one project runtime simultaneously,
- switch active workspaces safely and predictably,
- or evolve selected MCP services into true multi-tenant shared services.

We need an architecture that preserves the repository’s namespaced harness isolation model while adding first-class support for:

1. multiple installed workspaces,
2. multiple concurrently running workspace stacks through generated host port maps,
3. VS Code MCP configuration that follows the effective runtime endpoints,
4. and a deliberate path toward multi-tenant MCP services where that model is appropriate.

## Goals

- Allow multiple installed factory workspaces on one host without port collisions.
- Allow multiple runtime stacks to run concurrently when their host ports differ.
- Make workspace-local VS Code MCP settings derive from the effective runtime configuration rather than hardcoded default ports.
- Keep single-repo MCP services isolated until they are explicitly redesigned for tenancy.
- Add an explicit host-level concept of installed workspaces, running workspaces, and active workspaces.
- Define a path to multi-tenant MCP services that is secure, testable, and backward compatible.

## Non-Goals

- Rewriting every MCP server into a shared multi-tenant service in one step.
- Replacing the namespace-first installation model.
- Removing the current single-workspace runtime flow before a compatible migration path exists.
- Introducing central cloud control planes or external orchestration dependencies.

## Architectural Principles

### 1. Workspace Identity Is Explicit

Every installed workspace must have a durable identity. The host runtime must never infer tenancy only from the current working directory.

### 2. One Source of Truth for Effective Runtime Endpoints

The same configuration source must drive:

- Docker port publishing,
- VS Code MCP URLs,
- runtime verification,
- and active-workspace inspection.

### 3. Single-Tenant by Default, Multi-Tenant by Design

Services that mount `/target` or assume one repository root remain workspace-scoped until they are deliberately redesigned. Multi-tenancy is an opt-in capability, not an accidental side effect.

### 4. Active Workspace Is an Operator Concept, Not a Port Assumption

A workspace becomes active because the operator starts or selects it, not because it happens to own the default localhost ports.

### 5. Shared Services Must Prove Isolation

Any service promoted to multi-tenant/shared status must provide tenant-aware routing, storage isolation, audit separation, and deterministic verification.

## Current Constraints

### Fixed VS Code MCP URLs

The canonical MCP settings file currently points to fixed `127.0.0.1` URLs. This prevents one installed workspace from automatically advertising its own port map.

### Workspace-Scoped MCP Servers

Several services are intentionally repository-scoped and mount exactly one target tree at `/target`, for example:

- bash gateway,
- repo fundamentals servers,
- offline docs,
- GitHub ops,
- devops MCP servers.

These should be treated as single-tenant per container instance.

### Verification Assumes Default Ports

Runtime verification probes default host ports for health and endpoint reachability. That model must be replaced with generated effective endpoints.

## Target Architecture

### 1. Host Control Plane

A host-level control plane manages installed workspaces and runtime metadata.

### Required concepts

- `FACTORY_INSTANCE_ID`: unique per installed workspace.
- `PROJECT_WORKSPACE_ID`: stable logical workspace identifier.
- host registry file: records installed workspaces, paths, compose project names, port blocks, status, and timestamps.

### Registry responsibilities

- list installed workspaces,
- list running workspaces,
- detect stale entries,
- reserve and release port blocks,
- record the last selected workspace for operator convenience,
- support active-workspace inspection without mutating projects.

A suitable initial location is a host-scoped user data path rather than a project-local file.

### 2. Workspace Runtime Plane

Each installed workspace owns a runtime envelope.

### Workspace-scoped envelope

- namespaced install under `.copilot/softwareFactoryVscode/`,
- host contract in `.copilot/softwareFactoryVscode/.factory.env`,
- compose project name,
- generated host port block,
- generated workspace MCP settings,
- workspace-local mount at `/target`.

### Port allocation model

Each workspace receives a port block and uses deterministic offsets for all exposed services.

Example conceptual mapping:

- context7
- bash gateway
- repo fundamentals servers
- devops servers
- offline docs
- GitHub ops
- memory
- agent bus
- approval gate
- mock gateway / TUI

The important design rule is not the exact numeric range, but that the block is:

- unique per running workspace,
- generated once and persisted,
- collision-checked before stack startup,
- and reversible into concrete MCP URLs.

### 3. VS Code Workspace Plane

VS Code should consume generated effective MCP endpoints, not compile-time defaults.

### Required behavior

- The canonical config remains the schema/template source.
- The installed workspace generates concrete URLs from the effective port mapping.
- The generated workspace settings may also include tenant-specific headers where shared services require them.

### Result

Two VS Code windows can point to two different running workspaces on the same host, even when both use the same server names like `bashGateway`, because the URLs differ per workspace.

### 4. Hybrid Tenancy Model for MCP Services

The runtime should explicitly support two service classes.

### Class A: Workspace-Scoped Single-Tenant Services

These services remain one-container-per-workspace because they depend on a bound repository root or direct project filesystem state.

Examples:

- bash gateway,
- repo fundamentals services,
- offline docs,
- GitHub ops,
- docker-compose MCP,
- test runner MCP.

These services scale horizontally by running one isolated instance per workspace.

### Class B: Shared Multi-Tenant Services

These services may evolve toward one shared service that routes requests by tenant/workspace identity.

Likely candidates:

- `mcp-memory`,
- `mcp-agent-bus`,
- `approval-gate`.

A shared service must require tenant identity on every request, for example through generated headers or a session-bound tenant contract.

### Tenant contract requirements

A multi-tenant service must isolate:

- storage,
- request routing,
- logs,
- audit trails,
- and health/debug visibility.

A request for tenant A must never observe tenant B state.

## Active Workspace Semantics

The architecture should distinguish three states:

### Installed workspace

A repository contains a valid namespace-first factory install.

### Running workspace

The workspace runtime stack currently owns host ports and has active containers.

### Active workspace

The workspace is currently selected by the operator or current VS Code window for interaction.

Important: with generated port maps, more than one workspace can be running simultaneously. “Active” becomes a UX and routing concept, not a proof of exclusive runtime ownership.

## Robustness Requirements

- Detect port collisions before runtime startup.
- Recover from stale registry entries after crashes or forced Docker cleanup.
- Regenerate workspace settings idempotently.
- Keep static install verification independent from runtime startup.
- Make runtime verification read the effective port map, not hardcoded defaults.
- Preserve backward compatibility for existing installs during migration.
- Provide a clear fallback path when a requested port block cannot be allocated.

## Security and Isolation Requirements for Multi-Tenant Services

Any shared MCP service must satisfy the following before being treated as production-ready:

- explicit tenant identity per request,
- no default tenant fallback for cross-workspace requests,
- storage partitioning by tenant key,
- request and audit correlation by tenant key,
- administrative introspection that cannot leak tenant payloads by default,
- regression tests for cross-tenant isolation,
- and operator-visible diagnostics for active tenants and mapped workspaces.

## Migration Strategy

### Phase 1: Workspace-Scoped Port Generation

- add per-workspace port variables to `.copilot/softwareFactoryVscode/.factory.env`,
- generate effective MCP URLs into workspace settings,
- make verification consume generated URLs and health ports.

### Phase 2: Host Registry and Active Workspace Commands

- add registry-backed list/start/stop/activate/deactivate commands,
- integrate throwaway validation and runtime switching with the registry,
- expose operator-readable active-workspace state.

### Phase 3: Shared-Service Promotion

- promote selected services to tenant-aware shared mode,
- keep workspace-scoped services isolated,
- add explicit tenant headers and verification rules.

### Phase 4: Optional Runtime Optimization

- reduce duplicate per-workspace infrastructure where shared services are proven safe,
- keep workspace-scoped data plane services one-per-workspace.

## Decision Summary

The recommended architecture is a hybrid model:

- multiple installed workspaces,
- multiple concurrently running stacks through generated host port blocks,
- generated workspace-local VS Code MCP URLs,
- workspace-scoped MCP data plane services by default,
- and a controlled path to multi-tenant shared control plane services.

This design solves the immediate multi-project problem without forcing unsafe multi-tenancy on services that are currently repository-bound.
