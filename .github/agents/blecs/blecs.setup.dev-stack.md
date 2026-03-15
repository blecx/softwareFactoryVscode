---
description: blecs extension - start and validate backend+client dev stack with docker parity checks.
---

# blecs.setup.dev-stack

Run the standardized setup + startup + validation loop for this multirepo workspace.

Required flow:

1. Verify backend and client preconditions.
2. Start supervised dev stack for backend + frontend.
3. Run smoke checks for integrated services.
4. Rebuild docker images for API + web and verify health endpoints.
5. Report pass/fail with exact commands and outputs.

Validation targets:

- Backend API health (`http://localhost:8000/health`)
- Web app root (`http://localhost:8080/`)
- Web proxied API health (`http://localhost:8080/api/health`)
- Context7 MCP (`http://localhost:3010` when enabled)

Guardrails:

- Keep checks backend+client inclusive (never backend-only).
- Use workspace `.tmp/` for temporary artifacts.
- Do not modify `projectDocs/` or `configs/llm.json`.

User request:
$ARGUMENTS
