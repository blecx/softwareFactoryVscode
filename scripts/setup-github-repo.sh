#!/bin/bash
set -e

echo "========================================="
echo "⚙️ Configuring GitHub Repository for Software Factory Edge"
echo "========================================="

# Ensure GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ ERROR: GitHub CLI ('gh') is not installed."
    echo "Please install it from https://cli.github.com/ and run 'gh auth login' before executing this script."
    exit 1
fi

# Ensure user is authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ ERROR: You are not logged into GitHub CLI."
    echo "Please run 'gh auth login' first."
    exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "➡️ Setting up repository: $REPO"

echo "ℹ️ Enabling issues and auto-deletion of branches on merge..."
gh repo edit "$REPO" \
  --enable-issues=true \
  --delete-branch-on-merge=true

echo "ℹ️ Configuring Branch Protection for 'main'..."
# Create a JSON payload for the GraphQL / API update
# This enforces PRs, passing CI, and stops direct pushes.
cat << 'JSON' > /tmp/branch-protection-payload.json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Python Code Quality (Lint & Format)",
      "Architectural Boundary Tests",
      "PR Template Conformance"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/"$REPO"/branches/main/protection \
  --input /tmp/branch-protection-payload.json > /dev/null

rm /tmp/branch-protection-payload.json

echo "✅ Success! Branch protection rules and repo settings are now active."
echo "AI Agents will now be blocked if they attempt to bypass the CI or PR templates."
