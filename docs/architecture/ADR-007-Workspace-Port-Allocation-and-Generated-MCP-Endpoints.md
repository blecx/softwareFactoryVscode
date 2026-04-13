# ADR-007: Workspace Port Allocation and Generated MCP Endpoints

## Status

Accepted

## Context

The runtime now supports generated per-workspace host-port maps, but those effective endpoints are only reliable when every consumer follows the same installed-workspace runtime contract. Historically, fixed localhost defaults and source-checkout settings could drift from the generated installed-workspace URLs, creating competing runtime contracts.

## Decision

We will make effective runtime endpoints workspace-specific and generated.

### 1. Workspace installs must persist effective port values

- **Rule:** Each installed workspace MUST have a persisted runtime port map.
- **Rule:** Port values MUST be stored in namespaced install/runtime metadata available to bootstrap, runtime start, VS Code settings generation, and verification, including `.copilot/softwareFactoryVscode/.factory.env` and the generated runtime manifest.
- **Rule:** Port allocation MUST be collision-checked before a runtime stack starts.

### 2. VS Code MCP settings must be generated from effective runtime metadata

- **Rule:** `.copilot/config/vscode-agent-settings.json` remains the canonical schema/template source, but installed workspace settings and generated `software-factory.code-workspace` files MUST use concrete URLs derived from the workspace’s effective port map.
- **Rule:** The generated workspace file, runtime manifest, Docker Compose publishing contract, and runtime verifier MUST all derive from the same effective runtime metadata.
- **Rule:** Hardcoded default localhost MCP URLs MUST NOT remain the only runtime source of truth for installed workspaces.

### 3. Source-checkout settings must not create a second runtime contract

- **Rule:** Source-checkout `.vscode/settings.json` MAY mirror editor preferences, but it MUST NOT commit a second static MCP server block that competes with installed workspace runtime URLs.
- **Rule:** Runtime operations launched from the source checkout MUST resolve to the installed workspace’s generated runtime metadata rather than inventing new localhost defaults.

### 4. Verification must consume generated effective endpoints

- **Rule:** Runtime verification MUST read the same effective endpoint data used by VS Code and Docker Compose.
- **Rule:** Health probes and MCP reachability checks MUST follow configured workspace ports instead of assuming defaults.

## Consequences

- Multiple workspace stacks can run concurrently on one host when they use different port maps.
- VS Code windows can connect to different workspaces without endpoint collisions.
- Install and runtime verification become more reliable because they follow generated effective configuration rather than compile-time defaults.
- Source-checkout editor settings no longer compete with installed-workspace runtime endpoints.
