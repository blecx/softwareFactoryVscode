#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT_PATH = Path(".tmp/github-issue-queue-state.md")
DEFAULT_OUTPUT_PATH = Path(".tmp/interruption-recovery-snapshot.md")
CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def resolve_repo_relative_path(repo_root: Path, candidate: Path) -> Path:
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def resolve_output_path(repo_root: Path, candidate: Path) -> Path:
    output_path = resolve_repo_relative_path(repo_root, candidate)
    tmp_root = (repo_root / ".tmp").resolve()
    try:
        output_path.relative_to(tmp_root)
    except ValueError as exc:
        raise ValueError(
            "Recovery snapshots must be written under the repository-owned `.tmp/` directory."
        ) from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def parse_queue_checkpoint(checkpoint_path: Path) -> dict[str, str]:
    if not checkpoint_path.exists():
        return {}

    state: dict[str, str] = {}
    for raw_line in checkpoint_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        state[key.strip()] = value.strip()
    return state


def run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("GH_PAGER", "cat")
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def render_command_result(
    title: str,
    command: Sequence[str],
    result: subprocess.CompletedProcess[str],
) -> str:
    output = (result.stdout or "") + (result.stderr or "")
    output = output.rstrip() or "(no output)"
    return (
        f"### {title}\n\n"
        f"- Command: `{shlex.join(command)}`\n"
        f"- Exit code: {result.returncode}\n\n"
        f"```text\n{output}\n```\n"
    )


def collect_git_sections(repo_root: Path, runner: CommandRunner) -> list[str]:
    branch_command = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    status_command = ["git", "status", "--short", "--branch"]
    branch_result = runner(branch_command, repo_root)
    status_result = runner(status_command, repo_root)
    return [
        render_command_result("Current branch", branch_command, branch_result),
        render_command_result("Working tree state", status_command, status_result),
    ]


def collect_github_sections(
    repo_root: Path,
    *,
    active_issue: str | None,
    active_pr: str | None,
    runner: CommandRunner,
) -> list[str]:
    sections: list[str] = []

    if active_issue:
        issue_command = [
            "gh",
            "issue",
            "view",
            str(active_issue),
            "--json",
            "state,url,title,closedAt",
        ]
        sections.append(
            render_command_result(
                f"Issue #{active_issue} GitHub truth",
                issue_command,
                runner(issue_command, repo_root),
            )
        )
    else:
        sections.append(
            "### Issue GitHub truth\n\n- No active issue was recorded in the queue checkpoint.\n"
        )

    if active_pr and active_pr.lower() != "none":
        pr_view_command = [
            "gh",
            "pr",
            "view",
            str(active_pr),
            "--json",
            "state,isDraft,mergeable,url,headRefName,baseRefName,mergedAt",
        ]
        pr_checks_command = ["gh", "pr", "checks", str(active_pr)]
        sections.append(
            render_command_result(
                f"PR #{active_pr} GitHub truth",
                pr_view_command,
                runner(pr_view_command, repo_root),
            )
        )
        sections.append(
            render_command_result(
                f"PR #{active_pr} check state",
                pr_checks_command,
                runner(pr_checks_command, repo_root),
            )
        )
    else:
        sections.append(
            "### PR GitHub truth\n\n- No active PR was recorded in the queue checkpoint.\n"
        )

    return sections


def collect_runtime_section(
    repo_root: Path,
    *,
    include_runtime_status: bool,
    runner: CommandRunner,
) -> str:
    if not include_runtime_status:
        return (
            "## Runtime / service snapshot\n\n"
            "- Runtime diagnostics were not requested. Re-run with "
            "`--include-runtime-status` when the interrupted task touched Docker, "
            "MCP, or workspace lifecycle state.\n"
        )

    runtime_command = [
        sys.executable,
        str((repo_root / "scripts" / "factory_stack.py").resolve()),
        "status",
        "--repo-root",
        str(repo_root),
    ]
    return "## Runtime / service snapshot\n\n" + render_command_result(
        "factory_stack runtime status",
        runtime_command,
        runner(runtime_command, repo_root),
    )


def render_queue_checkpoint_section(
    checkpoint_state: dict[str, str],
    checkpoint_path: Path,
) -> str:
    lines = ["## Queue checkpoint", ""]
    if not checkpoint_state:
        lines.append(f"- Queue checkpoint not found at `{checkpoint_path}`.")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"- checkpoint_file: `{checkpoint_path}`")
    for key, value in checkpoint_state.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def render_resume_checklist(
    active_issue: str | None,
    active_pr: str | None,
    *,
    include_runtime_status: bool,
) -> str:
    lines = [
        "## Next resume checklist",
        "",
        "1. Compare the queue checkpoint with the GitHub truth sections above.",
        "2. Update `.tmp/github-issue-queue-state.md` before continuing "
        "implementation, merge, cleanup, or queue selection.",
    ]
    if active_issue:
        lines.append(
            f"3. Resume only issue `#{active_issue}` unless the operator "
            "explicitly approves moving to the next issue."
        )
    else:
        lines.append(
            "3. Identify the active issue before continuing any implementation "
            "or merge action."
        )
    if active_pr and active_pr.lower() != "none":
        lines.append(
            f"4. Re-check PR `#{active_pr}` state immediately before any merge "
            "or close narration."
        )
    else:
        lines.append(
            "4. If no PR exists yet, continue only with implementation/validation "
            "steps for the active issue."
        )
    lines.append(
        "5. If VS Code reloaded, the window closed/reopened, or the foreground "
        "task exited, do not assume the runtime stopped; compare against "
        "`factory_stack.py status` or the runtime snapshot before deciding "
        "whether start/stop/recovery is needed."
    )
    if include_runtime_status:
        lines.append(
            "6. Use the runtime snapshot section above to decide whether "
            "infrastructure recovery is required before resuming the task."
        )
    else:
        lines.append(
            "6. Re-run this helper with `--include-runtime-status` if the "
            "interrupted task touched runtime or MCP services."
        )
    lines.append("")
    return "\n".join(lines)


def capture_recovery_snapshot(
    *,
    repo_root: Path,
    checkpoint_path: Path,
    output_path: Path,
    active_issue: str | None = None,
    active_pr: str | None = None,
    include_runtime_status: bool = False,
    runner: CommandRunner = run_command,
    generated_at: str | None = None,
) -> Path:
    repo_root = repo_root.resolve()
    checkpoint_path = resolve_repo_relative_path(repo_root, checkpoint_path)
    output_path = resolve_output_path(repo_root, output_path)
    checkpoint_state = parse_queue_checkpoint(checkpoint_path)

    active_issue = active_issue or checkpoint_state.get("active_issue")
    active_pr = active_pr or checkpoint_state.get("active_pr")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )

    parts = [
        "# Interruption recovery snapshot",
        "",
        f"- generated_at: {generated_at}",
        f"- repo_root: `{repo_root}`",
        f"- output_file: `{output_path}`",
        f"- runtime_status_requested: {str(include_runtime_status).lower()}",
        "",
        render_queue_checkpoint_section(checkpoint_state, checkpoint_path),
        "## Local git state",
        "",
        *collect_git_sections(repo_root, runner),
        "## GitHub truth",
        "",
        *collect_github_sections(
            repo_root,
            active_issue=active_issue,
            active_pr=active_pr,
            runner=runner,
        ),
        collect_runtime_section(
            repo_root,
            include_runtime_status=include_runtime_status,
            runner=runner,
        ),
        render_resume_checklist(
            active_issue,
            active_pr,
            include_runtime_status=include_runtime_status,
        ),
    ]

    output_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a repo-owned recovery snapshot for interrupted issue workflows."
    )
    parser.add_argument(
        "--repo-root",
        default=str(SCRIPT_REPO_ROOT),
        help="Repository root used to resolve .tmp paths and local commands.",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=str(DEFAULT_CHECKPOINT_PATH),
        help="Queue checkpoint file to read before capturing recovery state.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=(
            "Output snapshot path. Must live under the repository-owned `.tmp/` "
            "directory."
        ),
    )
    parser.add_argument(
        "--issue",
        default="",
        help=(
            "Optional active issue override when the queue checkpoint is missing "
            "or stale."
        ),
    )
    parser.add_argument(
        "--pr",
        default="",
        help=(
            "Optional active PR override when the queue checkpoint is missing or "
            "stale."
        ),
    )
    parser.add_argument(
        "--include-runtime-status",
        action="store_true",
        help="Also capture `factory_stack.py status` output for runtime-sensitive work.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    capture_recovery_snapshot(
        repo_root=repo_root,
        checkpoint_path=Path(args.checkpoint_file),
        output_path=Path(args.output),
        active_issue=args.issue.strip() or None,
        active_pr=args.pr.strip() or None,
        include_runtime_status=args.include_runtime_status,
    )
    print("Recovery snapshot written to .tmp/interruption-recovery-snapshot.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
