# blecs Command Extensions

This directory contains blecs namespace command prompts (`blecs.*`) that extend the core Spec Kit-compatible flow.

Current extensions focus on:

- UX authority planning/review
- Workflow context packet generation
- Setup/startup and multirepo stack validation

Available commands:

- `create-issue`
- `resolve-issue`
- `pr-merge`
- `queue-backend`
- `queue-phase-2`
- `blecs.queue-backend`
- `blecs.queue-phase-2`
- `blecs.workflow.sync`
- `blecs.ux.plan`
- `blecs.ux.review`
- `blecs.setup.dev-stack`

Legacy shell loops such as `scripts/work-issue.py` and `scripts/issue-pr-merge-cleanup-loop.sh`
are deprecated and are not the canonical workflow.
