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
REPO_SURFACE_MARKERS = (
    ".github",
    "docs",
    "scripts",
    "tests",
    "README.md",
    "pytest.ini",
)
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


def inspect_execution_surface(repo_root: Path, surface_path: Path | None) -> dict[str, str | bool]:
    repo_root = repo_root.resolve()
    candidate = (surface_path or repo_root).expanduser().resolve()
    surface_dir = candidate if candidate.is_dir() else candidate.parent
    queue_root = (repo_root / ".tmp" / "queue-worktrees").resolve()

    try:
        relative_queue_path = surface_dir.relative_to(queue_root)
    except ValueError:
        relative_queue_path = None

    if surface_dir == repo_root:
        return {
            "surface_path": str(candidate),
            "surface_dir": str(surface_dir),
            "surface_root": str(repo_root),
            "surface_kind": "repo-root",
            "safe_to_resume": True,
            "note": (
                "The current surface resolves to the repository root, which is a "
                "valid re-anchor point. Continue only after `.tmp/github-issue-queue-state.md` "
                "and GitHub truth agree on the active issue/PR state."
            ),
        }

    if repo_root in surface_dir.parents:
        if relative_queue_path is not None and relative_queue_path.parts:
            queue_surface_root = queue_root / relative_queue_path.parts[0]
            has_git_dir = (queue_surface_root / ".git").exists()
            marker_count = sum(
                1
                for marker in REPO_SURFACE_MARKERS
                if (queue_surface_root / marker).exists()
            )
            if has_git_dir and marker_count == len(REPO_SURFACE_MARKERS):
                return {
                    "surface_path": str(candidate),
                    "surface_dir": str(surface_dir),
                    "surface_root": str(queue_surface_root),
                    "surface_kind": "queue-worktree",
                    "safe_to_resume": True,
                    "note": (
                        "The current surface is a full queue worktree rooted inside `.tmp/queue-worktrees/`. "
                        "Resume only after confirming it matches the active issue recorded in `.tmp/github-issue-queue-state.md`."
                    ),
                }

            return {
                "surface_path": str(candidate),
                "surface_dir": str(surface_dir),
                "surface_root": str(queue_surface_root),
                "surface_kind": "partial-queue-snapshot",
                "safe_to_resume": False,
                "note": (
                    "The current surface lives under `.tmp/queue-worktrees/` but is missing the repo/worktree markers "
                    "required for safe execution (for example `.git`, `docs/`, or `scripts/`). Treat it as a stray partial snapshot, not a valid resume surface. "
                    "Re-anchor from the repository root and the active worktree recorded in `.tmp/github-issue-queue-state.md`."
                ),
            }

        return {
            "surface_path": str(candidate),
            "surface_dir": str(surface_dir),
            "surface_root": str(repo_root),
            "surface_kind": "repo-subpath",
            "safe_to_resume": True,
            "note": (
                "The current surface is inside the repository checkout. Treat the editor/file path as advisory only and resume from the active issue/PR recorded in `.tmp/github-issue-queue-state.md`."
            ),
        }

    return {
        "surface_path": str(candidate),
        "surface_dir": str(surface_dir),
        "surface_root": str(surface_dir),
        "surface_kind": "outside-repo",
        "safe_to_resume": False,
        "note": (
            "The current surface is outside the repository root. Do not resume from it; re-anchor from the repository root and `.tmp/github-issue-queue-state.md` instead."
        ),
    }


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


def render_execution_surface_section(
    surface_assessment: dict[str, str | bool],
) -> str:
    lines = ["## Execution surface assessment", ""]
    lines.append(f"- surface_path: `{surface_assessment['surface_path']}`")
    lines.append(f"- surface_dir: `{surface_assessment['surface_dir']}`")
    lines.append(f"- surface_root: `{surface_assessment['surface_root']}`")
    lines.append(f"- surface_kind: `{surface_assessment['surface_kind']}`")
    lines.append(
        "- safe_to_resume: "
        + str(bool(surface_assessment["safe_to_resume"])).lower()
    )
    lines.append(f"- note: {surface_assessment['note']}")
    lines.append("")
    return "\n".join(lines)


def render_resume_checklist(
    active_issue: str | None,
    active_pr: str | None,
    *,
    include_runtime_status: bool,
    surface_assessment: dict[str, str | bool],
) -> str:
    lines = [
        "## Next resume checklist",
        "",
        "1. Compare the queue checkpoint with the GitHub truth sections above.",
    ]
    if not bool(surface_assessment["safe_to_resume"]):
        lines.append(
            "2. Do not resume from the current surface path; it was classified as `"
            f"{surface_assessment['surface_kind']}`. Re-anchor from the repository root and the active worktree recorded in `.tmp/github-issue-queue-state.md`."
        )
        next_index = 3
    else:
        next_index = 2

    lines.append(
        f"{next_index}. Update `.tmp/github-issue-queue-state.md` before continuing "
        "implementation, merge, cleanup, or queue selection.",
    )
    if active_issue:
        lines.append(
            f"{next_index + 1}. Resume only issue `#{active_issue}` unless the operator "
            "explicitly approves moving to the next issue."
        )
    else:
        lines.append(
            f"{next_index + 1}. Identify the active issue before continuing any implementation "
            "or merge action."
        )
    if active_pr and active_pr.lower() != "none":
        lines.append(
            f"{next_index + 2}. Re-check PR `#{active_pr}` state immediately before any merge "
            "or close narration."
        )
    else:
        lines.append(
            f"{next_index + 2}. If no PR exists yet, continue only with implementation/validation "
            "steps for the active issue."
        )
    lines.append(
        f"{next_index + 3}. If VS Code reloaded, the window closed/reopened, or the foreground "
        "task exited, do not assume the runtime stopped; compare against "
        "`factory_stack.py status` or the runtime snapshot before deciding "
        "whether start/stop/recovery is needed."
    )
    if include_runtime_status:
        lines.append(
            f"{next_index + 4}. Use the runtime snapshot section above to decide whether "
            "infrastructure recovery is required before resuming the task."
        )
    else:
        lines.append(
            f"{next_index + 4}. Re-run this helper with `--include-runtime-status` if the "
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
    surface_path: Path | None = None,
    runner: CommandRunner = run_command,
    generated_at: str | None = None,
) -> Path:
    repo_root = repo_root.resolve()
    checkpoint_path = resolve_repo_relative_path(repo_root, checkpoint_path)
    output_path = resolve_output_path(repo_root, output_path)
    checkpoint_state = parse_queue_checkpoint(checkpoint_path)
    surface_assessment = inspect_execution_surface(repo_root, surface_path)

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
        render_execution_surface_section(surface_assessment),
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
            surface_assessment=surface_assessment,
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
    parser.add_argument(
        "--surface-path",
        default="",
        help=(
            "Optional current editor/file/cwd path to classify as a resume surface. "
            "When omitted, the current working directory is assessed."
        ),
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
        surface_path=Path(args.surface_path).expanduser() if args.surface_path.strip() else None,
    )
    print("Recovery snapshot written to .tmp/interruption-recovery-snapshot.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
