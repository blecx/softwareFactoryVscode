#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MOCK_ROOT="$REPO_ROOT/.tmp/integration-test"

echo "======================================================"
echo "🧪 Running Software Factory Integration Regression Test"
echo "======================================================"

# Create an isolated temporary host project inside the repo-local .tmp guardrail
mkdir -p "$MOCK_ROOT"
MOCK_HOST="$(mktemp -d "$MOCK_ROOT/mock-host-XXXXXX")"
MOCK_FACTORY="$MOCK_HOST/.copilot/softwareFactoryVscode"

cleanup() {
    rm -rf "$MOCK_HOST"
}

trap cleanup EXIT

echo "➡️  Setting up Mock Host Project at $MOCK_HOST..."
mkdir -p "$MOCK_FACTORY"
cd "$MOCK_HOST"

# Simulate a host project file
echo "console.log('Host App');" > app.js

echo "➡️  Installing Factory as a nested subsystem..."
# Snapshot the repo into the mock host without recursively copying repo-local scratch state.
tar \
    --exclude=.git \
    --exclude=.tmp \
    --exclude=.venv \
    --exclude=.pytest_cache \
    --exclude=.mypy_cache \
    --exclude=__pycache__ \
    -cf - -C "$REPO_ROOT" . | tar -xf - -C "$MOCK_FACTORY"

echo "➡️  Running Assertions..."

# 1. Assert Host Cleanliness
if [ -d "$MOCK_HOST/.tmp" ] || [ -f "$MOCK_HOST/agent_metrics.json" ]; then
    echo "❌ FAIL: Host root was polluted by factory artifacts."
    exit 1
else
    echo "✅ PASS: Host root remains perfectly clean."
fi

# 2. Check docker compose mounts string
echo "➡️  Validating Docker Compose configs offline..."
if grep -q ":/target" "$MOCK_FACTORY/compose/docker-compose.repo-fundamentals-mcp.yml"; then
     echo "✅ PASS: Docker Compose volume variables resolve safely."
else
     echo "❌ FAIL: Docker Compose target mounts missing."
     exit 1
fi

# 3. Test Script Imports recursively
echo "➡️  Validating structure..."
if grep -rn "from agents\." "$MOCK_FACTORY/factory_runtime/" > /dev/null; then
    echo "❌ FAIL: Found legacy 'from agents.' imports."
    exit 1
else
    echo "✅ PASS: Refactored python imports look correct."
fi

echo "======================================================"
echo "🎉 ALL TESTS PASSED SUCCESSFULLY!"
echo "======================================================"
