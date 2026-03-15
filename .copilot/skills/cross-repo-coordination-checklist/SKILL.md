<skill>
<name>cross-repo-coordination-checklist</name>
<description>Active execution contract for maintaining API and UI synchronization between the backend and Client repositories.</description>
<file>
# Cross-Repo Coordination Checklist

## Objective
Provides actionable instructions for coordinating API contract changes between the factory backend and the separate factory-client frontend repository.

## When to Use
- Use this when modifying backend FastAPI routers, Pydantic models, or API endpoints.
- Use this when standardizing configurations that apply across both frontend and backend.

## When Not to Use
- Do not use this when the current task is isolated to pure internal backend logic, CLI tools, or documentation that does not affect the frontend API contract.

## Instructions

### 1. Impact Detection
Whenever a backend API contract (in `apps/api/routers/*.py` or `models.py`) is modified, verify the frontend impact:
- Search for impacted frontend API clients using `grep`:
  `grep -rnw "../factory-client/client/src/domain" -e "<Endpoint_or_Model_Name>"`
- If matching files are found, plan a complementary update for the client repository.

### 2. Cross-Linking Issues
When performing GitHub operations or creating PRs that span both repos, use explicit Markdown dependency syntax to link them:
- In the PR or Issue body, add: `Requires YOUR_ORG/YOUR_CLIENT_REPO#<ISSUE_NUMBER>`
- Ensure both the backend and client issues reference each other structurally.

### 3. Validation Routine
Before finalizing any cross-repo changes, validate the full stack works together:
1. Start the backend server:
   `cd apps/api && PROJECT_DOCS_PATH=../../projectDocs ../../.venv/bin/uvicorn main:app --reload`
2. Start the frontend developer server (in a separate terminal or background):
   `cd ../factory-client/client && npm run dev`
3. Execute the modified API workflow through the frontend UI or via API calls (using `curl` or tests) to confirm the contracts match.

### 4. Delivery Rules (Backward Compatibility)
- **Phase 1:** Deliver backend changes first. Prefer backward-compatible API additions (e.g., adding a new optional field).
- **Phase 2:** Deliver client integration updates after the backend is merged.
- **Phase 3:** If breaking changes are unavoidable, coordinate the deprecation pipeline and document the rollback strategy.

</file>
</skill>
