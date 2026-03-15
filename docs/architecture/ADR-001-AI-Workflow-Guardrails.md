# ADR-001: AI Workflow Guardrails & Operational Standards

## Status
Accepted

## Context
As the `softwareFactoryVscode` uses autonomous AI agents to parse issues, draft implementation plans, and write code, there is a risk of "drift" (hallucinated requirements, non-standard outputs, or corrupted local environments if agents skip processes). We must strictly enforce GitOps, GitHub Flow, and standard communication protocols.

## Decisions

### 1. Strict Template Rules (Gatekeeper Principle)
All inputs into the factory MUST follow the approved GitHub templates located in `.github/ISSUE_TEMPLATE` and `.github/pull_request_template.md`. 
*   **Rule:** If a user provides an unformatted prompt, unstructured text issue, or incomplete Pull Request, the Agent's *first* action must be to reject the request and ask the user to format it using the required template.
*   **Reason:** AI parsers rely on explicit `<headers>` or `## Sections` to segment context from acceptance criteria. Unstructured inputs lead to drift.

### 2. Mandatory GitHub Process
Any software development must comply entirely with standard GitHub Flow: `Issue` -> `Branch` -> `PR` -> `Review & CI` -> `Merge`.
*   **Rule:** Agents are forbidden from committing code directly to the `main` branch. 
*   **Rule:** Every task must be mapped to an Issue ID, and all work must occur on a branch named `issue-[id]`.

### 3. A2A Communication via Markdown/JSON
We reject complex heavyweight protocols for Agent-to-Agent (A2A) handoffs, and standardize strictly on **Markdown and JSON contracts**.
*   **Rule:** When a Planner Agent hands off context to a Coder Agent, the response must be structured in structured Markdown (using checklist primitives `[ ]`) or strictly typed JSON schemas.
*   **Rule:** Reasoning must be enclosed in `<thought_process>` XML tags so it is computationally ignored by downstream Coder agents, preventing contextual noise/drift.

### 4. Shift-Left CI & Pre-check Hooks
The CI pipeline (`.github/workflows/ci.yml`) is the ultimate arbiter of quality. However, to save remote compute and prevent agents from generating failing remote PRs, they must execute local validation.
*   **Rule:** Before agents invoke any command to finalize a Pull Request, they must execute local equivalents of CI (e.g. `tests/run-integration-test.sh` and `scripts/validate-pr-template.sh`) via their internal test terminals.

## Consequences
*   Agents must be explicitly prompted (via `.copilot/skills`) to enforce these rules.
*   Users must adhere to the formatting rules, removing "chat-like" ambiguous task creation in favor of disciplined GitOps issues.
