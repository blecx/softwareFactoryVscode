#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

create_venv() {
  if "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    return 0
  fi

  echo "⚠️  python -m venv could not create a usable environment; trying virtualenv ..."
  "$PYTHON_BIN" -m virtualenv "$VENV_DIR"
}

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "❌ Python 3 is required but was not found on PATH."
  exit 1
fi

echo "======================================================"
echo "🐍 Bootstrapping repository Python environment"
echo "======================================================"
echo "Repo:  $REPO_ROOT"
echo "Python: $PYTHON_BIN"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "➡️  Creating .venv ..."
  create_venv
else
  echo "➡️  Reusing existing .venv ..."
fi

VENV_PYTHON="$VENV_DIR/bin/python"

if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
  echo "➡️  Existing .venv is missing pip; rebuilding it ..."
  rm -rf "$VENV_DIR"
  create_venv
  VENV_PYTHON="$VENV_DIR/bin/python"
fi

echo "➡️  Upgrading pip ..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo "➡️  Installing runtime dependencies ..."
"$VENV_PYTHON" -m pip install -r "$REPO_ROOT/factory_runtime/agents/requirements.txt"

echo "➡️  Installing development/test dependencies ..."
"$VENV_PYTHON" -m pip install -r "$REPO_ROOT/requirements.dev.txt"

echo "✅ Repository environment ready: $VENV_DIR"
echo "Use: $VENV_PYTHON"