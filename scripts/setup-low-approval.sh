#!/bin/bash
# Configure VS Code command approval profiles in this workspace.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$ROOT_DIR/.tmp"

PROFILE="${1:-trusted-workflow}"

if [[ "$PROFILE" == "low-friction" || "$PROFILE" == "--low-friction" ]]; then
    PROFILE="low-friction"
elif [[ "$PROFILE" == "safe" || "$PROFILE" == "--safe" ]]; then
    PROFILE="safe"
else
    PROFILE="trusted-workflow"
fi

python3 "$SCRIPT_DIR/setup-vscode-autoapprove.py" --workspace-only --profile "$PROFILE"

echo ""
if [[ "$PROFILE" == "low-friction" ]]; then
    echo "✅ Low-friction HIGH-TRUST mode configured for workspace."
    echo "⚠️  Risks: ultra-broad command approvals can hide dangerous commands."
elif [[ "$PROFILE" == "trusted-workflow" ]]; then
    echo "✅ Trusted-workflow profile configured for workspace."
    echo "💡 To opt in to high-trust mode: $0 low-friction"
else
    echo "✅ Safe approval profile configured for workspace."
    echo "💡 To opt in to trusted-workflow mode: $0 trusted-workflow"
fi

echo ""
echo "📝 Reload VS Code: Ctrl+Shift+P -> Developer: Reload Window"
