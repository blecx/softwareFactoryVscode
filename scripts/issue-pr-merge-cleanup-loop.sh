#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALLOW_LEGACY_AUTONOMOUS_LOOP:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
The legacy issue/pr/merge shell loop is deprecated in this repository.

Use the Copilot-native workflow instead:
  - @create-issue
  - @resolve-issue
  - @pr-merge
  - @queue-backend or @queue-phase-2

See: docs/WORK-ISSUE-WORKFLOW.md

If you must invoke this historical script explicitly, set:
  ALLOW_LEGACY_AUTONOMOUS_LOOP=1
EOF
  exit 1
fi

MAX_ISSUES=25
ISSUE_OVERRIDE=""
DRY_RUN=0
SKIP_RECONCILE=0
NO_SPLIT_ISSUES=0
CURRENT_REPO=""

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p .tmp
exec 9>"$ROOT_DIR/.tmp/issue-pr-merge-cleanup.lock"
if ! flock -n 9; then
  echo "Another issue/pr/merge/cleanup loop is already running; stop it first." >&2
  exit 3
fi

usage() {
  cat <<'EOF'
Usage: ./scripts/issue-pr-merge-cleanup-loop.sh [options]

Loop workflow:
  select issue -> work-issue -> prmerge -> mandatory .tmp cleanup verify

Options:
  --issue <n>         Run one explicit issue first.
  --max-issues <n>    Stop after n issues (default: 25).
  --dry-run           Print actions only; do not execute.
  --skip-reconcile    Pass --skip-reconcile to next-issue.py selection.
  --no-split-issues   Do not pass --create-split-issues to work-issue.py.
  -h, --help          Show this help.

Cleanup policy (after successful merge):
  rm -f .tmp/pr-body-<issue>.md .tmp/issue-<issue>-*.md
  ls -la .tmp/*<issue>* 2>/dev/null || echo "✓ Cleanup verified"
EOF
}

resolve_repo() {
  if [[ -n "$CURRENT_REPO" ]]; then
    return 0
  fi

  CURRENT_REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
  if [[ -z "$CURRENT_REPO" ]]; then
    CURRENT_REPO=${TARGET_REPO:-YOUR_ORG/YOUR_REPO}
  fi
}

read_json_field() {
  local json_payload="$1"
  local field_name="$2"
  JSON_PAYLOAD="$json_payload" python3 -c '
import json
import sys
import os

field = sys.argv[1]
payload = os.environ.get("JSON_PAYLOAD", "").strip()
if not payload:
    raise SystemExit(0)
data = json.loads(payload)
value = data.get(field)
if value is None:
    raise SystemExit(0)
print(value)
' "$field_name"
}

find_existing_issue_from_local_draft() {
  resolve_repo

  local drafts=()
  while IFS= read -r draft; do
    drafts+=("$draft")
  done < <(find .tmp -maxdepth 1 -type f -name 'issue-*.md' ! -name 'issue-[0-9]*-*.md' | sort)

  if [[ ${#drafts[@]} -ne 1 ]]; then
    return 1
  fi

  local draft_path="${drafts[0]}"
  local title
  title="$(sed -n '1s/^# //p' "$draft_path")"
  if [[ -z "$title" ]]; then
    return 1
  fi

  local json_output issue_number issue_title slug pr_body_src
  json_output="$(gh issue list --repo "$CURRENT_REPO" --state open --limit 20 --search "$title in:title" --json number,title 2>/dev/null || true)"
  issue_number="$(JSON_PAYLOAD="$json_output" python3 -c '
import json
import os
import sys

title = sys.argv[1].strip().lower()
payload = os.environ.get("JSON_PAYLOAD", "").strip() or "[]"
matches = json.loads(payload)
for item in matches:
    candidate = str(item.get("title", "")).strip().lower()
    if candidate == title:
        print(item["number"])
        break
' "$title"
  )"

  if [[ -z "$issue_number" ]]; then
    return 1
  fi

  slug="$(basename "$draft_path" .md)"
  slug="${slug#issue-}"
  pr_body_src=".tmp/pr-body-${slug}.md"

  if [[ -f "$draft_path" && ! -f ".tmp/issue-${issue_number}-${slug}.md" ]]; then
    cp "$draft_path" ".tmp/issue-${issue_number}-${slug}.md"
  fi
  if [[ -f "$pr_body_src" && ! -f ".tmp/pr-body-${issue_number}.md" ]]; then
    cp "$pr_body_src" ".tmp/pr-body-${issue_number}.md"
  fi

  printf '%s|%s|%s\n' "$issue_number" "$title" "$draft_path"
}

verify_issue_exists() {
  local issue="$1"
  resolve_repo

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] Would verify issue #$issue in $CURRENT_REPO"
    return 0
  fi

  gh issue view "$issue" --repo "$CURRENT_REPO" --json number,state,title >/dev/null
}

require_option_value() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "$value" || "$value" =~ ^-- ]]; then
    echo "$option requires a value" >&2
    exit 1
  fi
}

is_valid_issue_number() {
  local value="$1"
  [[ "$value" =~ ^[1-9][0-9]*$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --issue)
      require_option_value "--issue" "${2:-}"
      ISSUE_OVERRIDE="$2"
      shift 2
      ;;
    --max-issues)
      require_option_value "--max-issues" "${2:-}"
      MAX_ISSUES="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --skip-reconcile)
      SKIP_RECONCILE=1
      shift
      ;;
    --no-split-issues)
      NO_SPLIT_ISSUES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! [[ "$MAX_ISSUES" =~ ^[0-9]+$ ]]; then
  echo "Invalid --max-issues value: $MAX_ISSUES" >&2
  exit 1
fi

if [[ -n "$ISSUE_OVERRIDE" ]] && ! is_valid_issue_number "$ISSUE_OVERRIDE"; then
  echo "Invalid --issue value: $ISSUE_OVERRIDE" >&2
  exit 1
fi

select_next_issue() {
  local next_cmd=(./scripts/next-issue.py)
  if [[ "$SKIP_RECONCILE" == "1" ]]; then
    next_cmd+=(--skip-reconcile)
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] Would run: ${next_cmd[*]}"
    echo "[dry-run] Using sample selected issue: 99999"
    return 0
  fi

  local output
  if ! output="$(${next_cmd[@]})"; then
    echo "$output"
    return 1
  fi

  echo "$output"

  local selected
  selected="$(printf '%s\n' "$output" | sed -n 's/.*Selected Issue: #\([0-9][0-9]*\).*/\1/p' | head -n1)"
  if [[ -z "$selected" ]]; then
    echo "Failed to parse selected issue number from next-issue output." >&2
    return 1
  fi

  printf '%s' "$selected"
}

run_work_issue() {
  local issue="$1"
  local cmd=(./scripts/work-issue.py --issue "$issue")
  if [[ "$NO_SPLIT_ISSUES" != "1" ]]; then
    cmd+=(--create-split-issues)
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] Would run: ${cmd[*]}"
    return 0
  fi

  set +e
  "${cmd[@]}"
  local rc=$?
  set -e
  return "$rc"
}

run_prmerge() {
  local issue="$1"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] Would run: ./scripts/prmerge $issue"
    return 0
  fi
  ./scripts/prmerge "$issue"
}

cleanup_issue_tmp() {
  local issue="$1"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] Would run: rm -f .tmp/pr-body-$issue.md .tmp/issue-$issue-*.md"
    echo "[dry-run] Would run: ls -la .tmp/*$issue* 2>/dev/null || echo \"✓ Cleanup verified\""
    return 0
  fi

  rm -f ".tmp/pr-body-${issue}.md" .tmp/issue-"${issue}"-*.md
  ls -la .tmp/*"${issue}"* 2>/dev/null || echo "✓ Cleanup verified"
}

count=0
while [[ "$count" -lt "$MAX_ISSUES" ]]; do
  issue=""
  if [[ -n "$ISSUE_OVERRIDE" ]]; then
    issue="$ISSUE_OVERRIDE"
    verify_issue_exists "$issue"
    ISSUE_OVERRIDE=""
  else
    existing_issue_info="$(find_existing_issue_from_local_draft || true)"
    if [[ -n "$existing_issue_info" ]]; then
      issue="${existing_issue_info%%|*}"
      existing_issue_title="$(printf '%s' "$existing_issue_info" | cut -d'|' -f2)"
      echo "Continuing existing issue #$issue from local draft: $existing_issue_title"
    else
      echo "Selecting next issue..."
      if [[ "$DRY_RUN" == "1" ]]; then
        select_next_issue
        issue="99999"
      else
        selection_output="$(select_next_issue)"
        issue="$(printf '%s\n' "$selection_output" | tail -n1)"
        printf '%s\n' "$selection_output" | sed '$d'
      fi
    fi
  fi

  if [[ -z "$issue" ]]; then
    echo "No issue selected; stopping loop."
    exit 1
  fi

  echo
  echo "========================================="
  echo "Loop item $((count + 1))/$MAX_ISSUES -> issue #$issue"
  echo "========================================="

  work_rc=0
  run_work_issue "$issue" || work_rc=$?

  if [[ "$work_rc" -eq 2 ]]; then
    echo "Issue #$issue triggered split-issues flow (exit=2). Skipping prmerge for parent issue."
    cleanup_issue_tmp "$issue"
    count=$((count + 1))
    continue
  fi

  if [[ "$work_rc" -ne 0 ]]; then
    echo "work-issue failed for #$issue (exit=$work_rc); stopping loop."
    exit "$work_rc"
  fi

  if [[ -f ".tmp/pr-body-$issue.md" ]]; then
    echo "Using comprehensive PR handoff: .tmp/pr-body-$issue.md"
  fi
  run_prmerge "$issue"
  cleanup_issue_tmp "$issue"

  count=$((count + 1))
done

echo "Loop complete: processed $count issue(s)."
