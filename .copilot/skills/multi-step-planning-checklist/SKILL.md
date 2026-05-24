---
name: multi-step-planning-checklist
description: "A checklist for producing thorough implementation plans and requirements coverage matrices."
---

# Multi-Step Planning Checklist

## Objective
Provides the criteria and deliverables required when creating a multi-step execution plan for an issue or feature.

## When to Use
- You are generating a new implementation roadmap or requirements spec.
- You are breaking down a large feature or issue into actionable PR-sized slices.
- You need to verify if an existing plan covers all requirements and handles cross-repo dependencies.

## When Not to Use
- The issue is a small, single-file bug fix with no cross-dependencies.
- You are executing an already-approved plan rather than creating or auditing one.

## Constraints
- Keep issue slices PR-sized where possible.
- Include explicit in/out-of-scope boundaries.
- Add testable acceptance criteria and validation commands.
- Track cross-repo dependencies and ordering.

## Completion Contract
- Requirements spec file
- Requirements-to-issues coverage matrix
- Implementation roadmap (phases + dependencies)
- Prioritized issue list

Exit Criteria:
- 100% requirements mapped to issues.
- No unresolved blockers in execution order.
- Hand-off package is implementation-ready.
