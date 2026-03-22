# GitHub Repository Configuration for Software Factory

Because the `softwareFactoryVscode` heavily relies on GitHub Flow (GitOps) to manage AI agents, your GitHub repository must be configured to enforce the factory's safety boundaries. If the repository allows direct pushes to `main` or allows PRs to be merged without passing CI, an errant AI agent could bypass the guardrails and pollute the main branch.

## Automated Setup (Recommended)

You can run the provided GitHub CLI script to automatically configure your repository:

```bash
chmod +x scripts/setup-github-repo.sh
./scripts/setup-github-repo.sh
```

*(Note: Requires the GitHub CLI `gh` to be installed and authenticated: `gh auth login`)*

## Manual Setup Requirements

If you prefer to configure the repository manually via the GitHub Settings UI, ensure the following constraints are met:

### 1. General Settings

- **Enable Issues:** The AI orchestrator relies on GitHub Issues to track state.
- **Automatically delete head branches:** Enable this so merged `issue-*` branches are cleaned up, preventing the local VS Code workspace from becoming cluttered with stale AI branches.

### 2. Branch Protection Rules (Branch: `main`)

- **Require a pull request before merging:** Agents are instructed to work on branches. This strictly enforces that rule at the server level.
- **Require status checks to pass before merging:**
  - Require branches to be up to date before merging.
  - Add the following required status checks (these match the names in our `ci.yml`):
    - `Python Code Quality (Lint & Format)`
    - `Architectural Boundary Tests`
    - `PR Template Conformance`
- **Human approvals are an operator policy choice:** If you want a human in the loop, require `1` approval. If you want autonomous merge after CI passes, set the required approvals to `0`, but keep the status checks and PR review process intact in the workflow.
- **Include Administrators:** Enforce these rules for repository administrators as well, because the Personal Access Token (PAT) used by the AI usually has admin/write privileges.

### 3. Action Workflow Permissions

- Go to **Settings -> Actions -> General**.
- Under Workflow permissions, select **Read and write permissions** if your AI agents rely on GitHub Actions to auto-approve, label, or comment.
- Check **Allow GitHub Actions to create and approve pull requests**.
