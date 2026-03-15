#!/bin/bash
set -e

PR_BODY_FILE="$1"

if [ -z "$PR_BODY_FILE" ] || [[ "$PR_BODY_FILE" == "--body-file" ]]; then
    # Handle both old arg passing and new positional args
    if [[ "$1" == "--body-file" ]]; then
       PR_BODY_FILE="$2"
    else
       echo "Usage: $0 <path-to-pr-body.md>"
       exit 1
    fi
fi

if [ ! -f "$PR_BODY_FILE" ]; then
    echo "❌ ERROR: PR body file not found: $PR_BODY_FILE"
    exit 1
fi

echo "========================================="
echo "PR Template Validation"
echo "========================================="

errors=0

check_section() {
    local label="$1"
    local pattern="$2"
    if grep -Eqi "$pattern" "$PR_BODY_FILE"; then
        echo "✅ Found: $label"
    else
        echo "❌ Missing required section: $label"
        errors=$((errors + 1))
    fi
}

echo "ℹ️  Checking required sections..."
check_section "## Summary" "^##[[:space:]]+Summary"
check_section "## Linked issue" "^##[[:space:]]+Linked[[:space:]]+issue"
check_section "## Scope and affected areas" "^##[[:space:]]+Scope[[:space:]]+and[[:space:]]+affected[[:space:]]+areas"
check_section "## Validation / evidence" "^##[[:space:]]+Validation[[:space:]]*/[[:space:]]*evidence"
check_section "## Cross-repo impact" "^##[[:space:]]+Cross-repo[[:space:]]+impact"
check_section "## Follow-ups" "^##[[:space:]]+Follow-ups"

if [ $errors -gt 0 ]; then
    echo "========================================="
    echo "❌ FAILED: $errors error(s) found"
    echo "Please ensure the PR matches .github/pull_request_template.md exactly!"
    exit 1
else
    echo "========================================="
    echo "✅ PR Template Validation Passed!"
    exit 0
fi
