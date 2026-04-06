# ADR-007: Workspace Port Allocation and Generated MCP Endpoints

## Status

Proposed

## Context

The current runtime already supports Docker host-port overrides, but the effective MCP URLs used by VS Code and the runtime verifier are still treated as fixed localhost defaults. This prevents multiple workspaces from advertising distinct runtime endpoints reliably and makes verification drift-prone when ports are remapped.

## Decision

We will make effective runtime endpoints workspace-specific and generated.

### 1. Workspace installs must persist effective port values

- **Rule:** Each installed workspace MUST have a persisted runtime port map.
- **Rule:** Port values MUST be stored in install/runtime metadata available to bootstrap, runtime start, VS Code settings generation, and verification.
- **Rule:** Port allocation MUST be collision-checked before a runtime stack starts.

### 2. VS Code MCP settings must be generated from effective runtime metadata

- **Rule:** `.copilot/config/vscode-agent-settings.json` remains the canonical schema/template source, but installed workspace settings MUST use concrete URLs derived from the workspace’s effective port map.
- **Rule:** Hardcoded default localhost MCP URLs MUST NOT remain the only runtime source of truth for installed workspaces.

### 3. Verification must consume generated effective endpoints

- **Rule:** Runtime verification MUST read the same effective endpoint data used by VS Code and Docker Compose.
- **Rule:** Health probes and MCP reachability checks MUST follow configured workspace ports instead of assuming defaults.

## Consequences

- Multiple workspace stacks can run concurrently on one host when they use different port maps.
- VS Code windows can connect to different workspaces without endpoint collisions.
- Install and runtime verification become more reliable because they follow generated effective configuration rather than compile-time defaults.

