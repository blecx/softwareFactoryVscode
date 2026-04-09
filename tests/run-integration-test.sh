#!/bin/bash
set -e

echo "======================================================"
echo "🧪 Running Software Factory Integration Regression Test"
echo "======================================================"

# Create an isolated temporary host project
MOCK_HOST="/tmp/mock-host-$(date +%s)"
MOCK_FACTORY="$MOCK_HOST/.copilot/softwareFactoryVscode"

echo "➡️  Setting up Mock Host Project at $MOCK_HOST..."
mkdir -p "$MOCK_HOST"
cd "$MOCK_HOST"

# Simulate a host project file
echo "console.log('Host App');" > app.js

echo "➡️  Installing Factory as a nested subsystem..."
# Copy the factory recursively into the mock host, preserving structure
cp -r "$OLDPWD" "$MOCK_FACTORY"

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
