<skill>
<name>issue-creation-workflow</name>
<description>Workflow or rule module for creating new issues via GitHub CLI.</description>
<file>
# Issue Creation Workflow

## Objective
Provides context and instructions for the `issue-creation-workflow` skill module.

## When to Use
- Use this when working on tasks related to issue creation, tracking roadmap items, or writing specifications.

## When Not to Use
- Do not use this when the current task does not involve creating or plotting out GitHub issues.

## Instructions
1. Search for duplicates and related issues using `gh issue list`.
2. Select repository (backend/client) and estimate size (S/M/L).
3. Decide whether the work is a feature/enhancement or a bug/defect.
4. Draft issue body by strictly adhering to the matching template sections found in:
   - `.github/ISSUE_TEMPLATE/feature_request.yml` for features/enhancements
   - `.github/ISSUE_TEMPLATE/bug_report.yml` for defects
5. Add testable acceptance criteria and validation commands.
6. Add cross-repo impact and dependencies.
7. Save draft under `.tmp/issue-<number>-draft.md`, review, then create the issue explicitly using:
   `gh issue create --repo <repo> --title "<title>" --body-file .tmp/issue-<number>-draft.md`

## Required Sections
- Goal / Problem Statement
- Scope (In / Out / Dependencies)
- Acceptance Criteria
- API Contract (if applicable)
- Technical Approach
- Testing Requirements
- Documentation Updates

## Quality Checks
- Criteria are specific and measurable.
- No unresolved placeholders remain.
- Repo constraints included (`projectDocs/`, `configs/llm.json`).
- Cross-repo link exists when downstream work is needed.
- Selected issue template matches the issue type instead of defaulting every request to a feature template.

## Completion Contract
Return:
- selected repository,
- issue title,
- issue URL/number,
- short scope summary,
- implementation handoff note.
</file>
</skill>
