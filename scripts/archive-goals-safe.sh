#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISOR_PID_FILE="${DEV_STACK_PID_FILE:-$REPO_ROOT/.tmp/dev-stack-supervisor.pid}"
SUPERVISOR_SCRIPT="$REPO_ROOT/scripts/dev_stack_supervisor.py"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

was_running=false
supervisor_pid=""

is_running_pid() {
  local pid="$1"
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  kill -0 "$pid" 2>/dev/null
}

stop_supervisor_if_running() {
  if [[ ! -f "$SUPERVISOR_PID_FILE" ]]; then
    return 0
  fi

  supervisor_pid="$(tr -d '[:space:]' < "$SUPERVISOR_PID_FILE" || true)"
  if ! is_running_pid "$supervisor_pid"; then
    rm -f "$SUPERVISOR_PID_FILE"
    supervisor_pid=""
    return 0
  fi

  was_running=true
  echo "[archive-safe] stopping dev_stack_supervisor (pid=$supervisor_pid)"
  kill -TERM "$supervisor_pid" 2>/dev/null || true

  for _ in {1..30}; do
    if ! is_running_pid "$supervisor_pid"; then
      break
    fi
    sleep 0.2
  done

  if is_running_pid "$supervisor_pid"; then
    echo "[archive-safe] forcing dev_stack_supervisor stop (pid=$supervisor_pid)"
    kill -KILL "$supervisor_pid" 2>/dev/null || true
  fi

  rm -f "$SUPERVISOR_PID_FILE"
}

restart_supervisor_if_needed() {
  if [[ "$was_running" != true ]]; then
    return 0
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "[archive-safe] warning: python interpreter not found at $PYTHON_BIN; supervisor not restarted" >&2
    return 0
  fi

  echo "[archive-safe] restarting dev_stack_supervisor"
  nohup "$PYTHON_BIN" -u "$SUPERVISOR_SCRIPT" >/dev/null 2>&1 &
  sleep 0.4
}

stop_supervisor_if_running
trap 'restart_supervisor_if_needed' EXIT

bash "$REPO_ROOT/scripts/archive-goals.sh" "$@"
