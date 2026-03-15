<skill>
<name>plan-workflow</name>
<description>Workflow or rule module for bounded implementation planning, issue sizing, and dependency mapping.</description>
<file>
# Plan Workflow (Module)

## Objective
Provides context and instructions for the `plan-workflow` skill module.

Use this skill as the canonical implementation source for `Plan`.

## When to Use

- A feature, fix, or refactor needs a compact implementation plan before coding.
- Work should be split into issue-sized slices with explicit dependencies.
- A low-context research pass is needed without exhaustive codebase exploration.

## When Not to Use
- Do not use this when the current task does not involve plan workflow.

## Instructions

1. Define the goal in one line.
2. Bound discovery to a small set of high-signal files.
3. Identify existing patterns, constraints, and affected modules.
4. Break work into S/M/L issue slices with dependencies.
5. Produce a concise markdown plan ready for `resolve-issue` or `create-issue`.

## Required Plan Shape

- Goal
- Analysis
- Steps
- Dependencies
- Risks
- Validation notes

## Guardrails

- Prefer up to 5 high-signal files for initial discovery.
- Follow DDD boundaries and repository conventions.
- Use `.tmp/`, never `/tmp`, for optional plan artifacts.
- Do not implement code or open/merge PRs in this mode.

## Completion Contract

Return a concise plan summary that includes:

- goal,
- affected areas,
- ordered steps with size estimates,
- dependencies or blockers,
- handoff note for implementation.
</file>
</skill>
