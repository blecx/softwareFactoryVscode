#!/bin/bash

# Create Master
MASTER=$(gh issue create --title "umbrella: feat: close post-#532 follow-up hardening gaps without drift" --body "Master umbrella issue" | grep -oE '[0-9]+$')
echo "Master: $MASTER"

# Create Dependency Umbrellas
UMBA=$(gh issue create --title "umbrella: feat: complete preflight evidence lifecycle and break-glass workflow" --body "Dependency umbrella A for #$MASTER" | grep -oE '[0-9]+$')
UMBB=$(gh issue create --title "umbrella: feat: complete authoritative production-readiness evidence path" --body "Dependency umbrella B for #$MASTER" | grep -oE '[0-9]+$')

# Create W issues
W1=$(gh issue create --title "feat: define exact preflight evidence schema and consumer matrix" --body "Depends on #$UMBA" | grep -oE '[0-9]+$')
W2=$(gh issue create --title "feat: record issue-workflow evidence in work-issue and next-issue" --body "Depends on #$W1" | grep -oE '[0-9]+$')
W3=$(gh issue create --title "feat: record and refresh queue preflight evidence in step2 backend workflows" --body "Depends on #$W1, #$W2" | grep -oE '[0-9]+$')
W4=$(gh issue create --title "feat: complete prmerge force-bypass break-glass evidence flow" --body "Depends on #$W1" | grep -oE '[0-9]+$')
W5=$(gh issue create --title "feat: automate queue closeout residue cleanup and lifecycle tests" --body "Depends on #$W2, #$W3, #$W4" | grep -oE '[0-9]+$')

# Create R issues
R1=$(gh issue create --title "feat: remove dead GitHub history helper and unify authoritative fetch path" --body "Depends on #$UMBB" | grep -oE '[0-9]+$')
R2=$(gh issue create --title "feat: require canonical job set in strict readiness verification and streak evidence" --body "Depends on #$R1" | grep -oE '[0-9]+$')
R3=$(gh issue create --title "feat: make strict readiness aggregate fail closed with explicit repo/history diagnostics" --body "Depends on #$R1" | grep -oE '[0-9]+$')
R4=$(gh issue create --title "feat: align consecutive-green semantics with the production gate definition" --body "Depends on #$R1, #$R2" | grep -oE '[0-9]+$')
R5=$(gh issue create --title "feat: encode strict production docs contract in authoritative readiness scoring" --body "Depends on #$R2" | grep -oE '[0-9]+$')
R6=$(gh issue create --title "feat: add end-to-end authoritative readiness integration and above-90 contract tests" --body "Depends on #$R2, #$R3, #$R4, #$R5" | grep -oE '[0-9]+$')

echo "Queue created:"
echo "W1: $W1, R1: $R1"

cat << JSON > .tmp/github-issue-queue-state.md
# Queue Checkpoint

\`\`\`json
{
  "active_umbrella": $MASTER,
  "queue": [
    { "id": "W1", "issue_number": $W1, "title": "feat: define exact preflight evidence schema and consumer matrix", "status": "pending" },
    { "id": "R1", "issue_number": $R1, "title": "feat: remove dead GitHub history helper and unify authoritative fetch path", "status": "pending" }
  ]
}
\`\`\`
JSON
