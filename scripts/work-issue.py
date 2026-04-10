#!/usr/bin/env python3
"""
Work Issue - Main CLI for autonomous issue resolution

This is the primary interface for invoking the autonomous workflow agent.

Usage:
    ./scripts/work-issue.py --issue 26
    ./scripts/work-issue.py --issue 26 --dry-run
    ./scripts/work-issue.py --issue 26 --interactive
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    """Main entry point."""
    import argparse

    _ensure_venv_and_reexec()

    # Import after venv re-exec so dependencies are available
    from factory_runtime.agents.agent_registry import create_issue_agent
    from scripts.work_issue_split import generate_split_issue_stubs

    parser = argparse.ArgumentParser(
        description="Autonomous AI Agent for Issue Resolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The agent will:
  ✅ Fetch and analyze the issue
  ✅ Create implementation plan
  ✅ Write tests first, then implementation
  ✅ Run tests and fix failures
  ✅ Perform self-review
  ✅ Create pull request
  ✅ Update knowledge base

Examples:
  # Fully autonomous - agent works independently
  ./scripts/work-issue.py --issue 26

    # Dry run - initialize only (no LLM calls, no changes)
  ./scripts/work-issue.py --issue 26 --dry-run

        # Run with Ralph agent profile
        ./scripts/work-issue.py --issue 26 --agent ralph

    # Plan-only - Phase 1-2 planning only (LLM required, no changes)
    ./scripts/work-issue.py --issue 26 --plan-only

    # Use a specific LLM config (recommended for per-role Copilot models)
    LLM_CONFIG_PATH=configs/llm.hybrid.json.example \
        ./scripts/work-issue.py --issue 26 --plan-only
    # Or via flag:
    ./scripts/work-issue.py --issue 26 --plan-only --llm-config configs/llm.hybrid.json.example

  # Interactive - pause for approval between phases
  ./scripts/work-issue.py --issue 26 --interactive

Requirements:
    - Python 3.12+ (this repo enforces .venv via ./setup.sh)
  - GitHub CLI (gh) authenticated
  - Git configured
    - GitHub Models token provided via config or env vars (e.g. GITHUB_TOKEN or GH_TOKEN)

Goal Archiving:
    - Enabled by default (pre + post run): archives Goal sections from `.tmp/*.md`
    - Disable per run: `--no-goal-archive`
    - Disable via environment: `WORK_ISSUE_GOAL_ARCHIVE=0`

Token Budget Mode:
    - Compact prompt mode is enabled by default via `WORK_ISSUE_COMPACT=1`
    - Prompt insertion budget can be tuned with `WORK_ISSUE_MAX_PROMPT_CHARS` (default: 3200)
    - Set `WORK_ISSUE_COMPACT=0` only when your model endpoint supports larger request payloads
        """,
    )

    parser.add_argument(
        "--issue", type=int, required=True, help="GitHub issue number to work on"
    )

    parser.add_argument(
        "--agent",
        type=str,
        default="autonomous",
        help=(
            "Agent alias or class spec. Examples: 'autonomous', 'ralph', "
            "or 'module.path:ClassName'."
        ),
    )

    parser.add_argument(
        "--llm-config",
        type=str,
        default=None,
        help=(
            "Path to an LLM config JSON file. Sets LLM_CONFIG_PATH for this run. "
            "Useful for selecting hybrid configs without editing configs/llm.json."
        ),
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Initialize only (no LLM calls, no repo changes)",
    )

    mode_group.add_argument(
        "--plan-only",
        action="store_true",
        help="Run Phase 1-2 planning only (LLM required, no repo changes)",
    )

    parser.add_argument(
        "--interactive", action="store_true", help="Pause for approval between phases"
    )

    parser.add_argument(
        "--create-split-issues",
        action="store_true",
        help=(
            "When planning guardrail requires a split, generate and create split issues via gh CLI, "
            "then stop the loop."
        ),
    )

    parser.add_argument(
        "--split-issue-limit",
        type=int,
        default=3,
        help="Maximum number of split child issues to generate/create (default: 3)",
    )

    parser.add_argument(
        "--no-goal-archive",
        action="store_true",
        help="Disable automatic pre/post goal archiving from .tmp",
    )

    parser.add_argument(
        "--dev-stack",
        choices=["auto", "required", "off"],
        default=os.environ.get("WORK_ISSUE_DEV_STACK", "auto"),
        help=(
            "Development stack behavior before agent execution: "
            "'auto' (default) attempts to ensure backend+frontend are running, "
            "'required' fails fast if stack is not healthy, "
            "'off' skips dev-stack checks."
        ),
    )

    args = parser.parse_args()

    if args.llm_config:
        os.environ["LLM_CONFIG_PATH"] = args.llm_config

    os.environ.setdefault("WORK_ISSUE_PLANNING_FALLBACK_MODEL", "openai/gpt-4o-mini")
    os.environ.setdefault("WORK_ISSUE_PLANNING_FALLBACK_AFTER_ATTEMPT", "3")
    os.environ.setdefault("WORK_ISSUE_PLANNING_FALLBACK_MAX_ATTEMPTS", "6")
    os.environ.setdefault("WORK_ISSUE_PLANNING_FALLBACK_PROMPT_CHARS", "1400")
    os.environ.setdefault("WORK_ISSUE_MAX_RPS", "0.03")
    os.environ.setdefault("WORK_ISSUE_RPS_JITTER", "0.25")
    os.environ.setdefault("WORK_ISSUE_RATE_LIMIT_COOLDOWN_SECONDS", "120")

    archive_enabled = (
        not args.no_goal_archive
        and os.environ.get("WORK_ISSUE_GOAL_ARCHIVE", "1") != "0"
    )

    print(
        """
╔══════════════════════════════════════════════════════════════════╗
║        Autonomous Workflow Agent - AI-Powered Development        ║
║                  Powered by Microsoft Agent Framework            ║
╚══════════════════════════════════════════════════════════════════╝
"""
    )

    exit_code = 0

    if archive_enabled:
        _archive_goals(stage="pre", issue_number=args.issue)

    _ensure_github_models_token()

    # Check prerequisites
    if not _check_prerequisites():
        exit_code = 1

    # Create and run agent
    try:
        if exit_code != 0:
            return

        if not args.dry_run and not args.plan_only:
            dev_stack_ok = _ensure_dev_stack(mode=args.dev_stack)
            if not dev_stack_ok and args.dev_stack == "required":
                print(
                    "❌ Dev stack is required but not ready. "
                    "Fix startup issues or run with --dev-stack off/auto."
                )
                sys.exit(1)

        selected_agent = args.agent.strip()
        print(f"🧠 Agent profile: {selected_agent}")

        agent = create_issue_agent(
            agent_name_or_spec=selected_agent,
            issue_number=args.issue,
            dry_run=bool(args.dry_run or args.plan_only),
        )

        await agent.initialize()

        if args.dry_run:
            print(
                "✅ Dry run complete: initialization succeeded (no LLM calls executed)."
            )
            return

        max_attempts = int(os.environ.get("WORK_ISSUE_RATE_LIMIT_RETRIES", "4"))
        base_delay = int(os.environ.get("WORK_ISSUE_RATE_LIMIT_DELAY", "120"))

        if args.plan_only:
            _ = await _run_with_rate_limit_retry(
                agent.plan_only,
                max_attempts=max_attempts,
                base_delay=base_delay,
                operation="planning",
            )
            print(
                "✅ Plan-only complete: planning finished (no repo changes executed)."
            )
            return

        success = await _run_with_rate_limit_retry(
            agent.execute,
            max_attempts=max_attempts,
            base_delay=base_delay,
            operation="execution",
        )

        if (
            not success
            and args.create_split_issues
            and getattr(agent, "last_guardrail_triggered", False)
        ):
            parent_issue_body = _fetch_issue_body_via_gh(args.issue)
            split_drafts = generate_split_issue_stubs(
                parent_issue_number=args.issue,
                estimated_minutes=getattr(agent, "last_estimated_manual_minutes", None),
                recommendation_text=getattr(agent, "last_split_recommendation", ""),
                parent_issue_body=parent_issue_body,
                max_issues=max(1, args.split_issue_limit),
            )
            _persist_split_drafts(args.issue, split_drafts)
            created = _create_split_issues_via_gh(
                issue_number=args.issue,
                drafts=split_drafts,
                repo=os.environ.get(
                    "WORK_ISSUE_REPO",
                    os.environ.get("TARGET_REPO", "YOUR_ORG/YOUR_REPO"),
                ),
            )
            _cleanup_split_transient_files(args.issue)
            print(f"\nSPLIT_ISSUES_CREATED: {len(created)}")
            for created_issue in created:
                print(f"- {created_issue}")
            print("⏸️  Execution paused after split issue creation.")
            raise SystemExit(2)

        # Interactive mode
        if args.interactive and success:
            await _interactive_mode(agent)

        exit_code = 0 if success else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        exit_code = 1
    finally:
        if archive_enabled:
            _archive_goals(stage="post", issue_number=args.issue)

    sys.exit(exit_code)


async def _run_with_rate_limit_retry(
    func, max_attempts: int, base_delay: int, operation: str
):
    """Retry a coroutine on rate-limit errors with exponential backoff."""
    attempt = 1
    delay = base_delay
    while True:
        try:
            return await func()
        except Exception as exc:  # pragma: no cover - defensive guard
            message = str(exc).lower()
            is_rate_limit = any(
                token in message
                for token in [
                    "too many requests",
                    "ratelimit",
                    "rate limit",
                    "429",
                ]
            )
            if not is_rate_limit or attempt >= max_attempts:
                raise
            print(
                f"⚠️  Rate limit hit during {operation} (attempt {attempt}/{max_attempts}). "
                f"Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)
            delay *= 2
            attempt += 1


def _persist_split_drafts(issue_number: int, drafts: Sequence) -> None:
    """Persist split issue drafts for traceability/debugging."""
    output_path = Path(f".copilot/softwareFactoryVscode/.tmp/issue-{issue_number}-split-stubs.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "title": draft.title,
            "body": draft.body,
        }
        for draft in drafts
    ]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fetch_issue_body_via_gh(issue_number: int) -> str:
    """Fetch issue body text via gh CLI for split-step derivation."""
    from factory_runtime.agents.tooling.gh_throttle import run_gh_throttled

    cmd = [
        "gh",
        "issue",
        "view",
        str(issue_number),
        "--json",
        "body",
        "--jq",
        ".body",
    ]
    repo = (os.environ.get("WORK_ISSUE_REPO") or "").strip()
    if repo:
        cmd.extend(["--repo", repo])

    result = run_gh_throttled(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _create_split_issues_via_gh(
    issue_number: int, drafts: Sequence, repo: str
) -> list[str]:
    """Create split issues via gh CLI while skipping duplicate titles."""
    from factory_runtime.agents.tooling.gh_throttle import run_gh_throttled

    created: list[str] = []
    for draft in drafts:
        exists = run_gh_throttled(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--search",
                f'"{draft.title}" in:title',
                "--json",
                "number",
                "--jq",
                ".[0].number // empty",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        existing_number = (exists.stdout or "").strip()
        if existing_number:
            created.append(f"#{existing_number} (existing) {draft.title}")
            continue

        result = run_gh_throttled(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                draft.title,
                "--body",
                draft.body,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"⚠️  Failed to create split issue '{draft.title}': {(result.stderr or '').strip()}"
            )
            continue
        created.append((result.stdout or "").strip() or draft.title)

    if not created:
        print(
            f"⚠️  No split issues were created for #{issue_number}. "
            "Check gh authentication and repository permissions."
        )

    return created


def _cleanup_split_transient_files(issue_number: int) -> None:
    """Clean transient artifacts after split operation."""
    for path in Path(".copilot/softwareFactoryVscode/.tmp").glob(f"work-issue-{issue_number}-attempt-*.log"):
        try:
            path.unlink()
        except OSError:
            pass


def _check_prerequisites() -> bool:
    """Check that required tools are available."""
    import shutil
    import subprocess

    checks = []

    # Check gh CLI
    if shutil.which("gh"):
        checks.append(("GitHub CLI (gh)", "✅"))
    else:
        checks.append(
            ("GitHub CLI (gh)", "❌ Not found - install from https://cli.github.com")
        )

    # Check git
    if shutil.which("git"):
        checks.append(("Git", "✅"))
    else:
        checks.append(("Git", "❌ Not found"))

    # Check Python version
    import sys

    version = sys.version_info
    py_exec = sys.executable
    if version.major == 3 and version.minor >= 12:
        checks.append((f"Python {version.major}.{version.minor} ({py_exec})", "✅"))
    else:
        checks.append(
            (
                f"Python {version.major}.{version.minor} ({py_exec})",
                "❌ Need Python 3.12+",
            )
        )

    # Check LLM config
    config_path: Path
    env_path = (os.environ.get("LLM_CONFIG_PATH") or "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        config_path = p if p.is_absolute() else Path.cwd() / p
    elif Path("/config/llm.json").exists():
        config_path = Path("/config/llm.json")
    else:
        config_path = Path("configs/llm.json")
        if not config_path.exists():
            config_path = Path("configs/llm.default.json")

    if config_path.exists():
        checks.append((f"LLM config ({config_path})", "✅"))
    else:
        checks.append(
            (
                "LLM config",
                "❌ Set LLM_CONFIG_PATH or create configs/llm.json",
            )
        )

    # Check GitHub Models token availability (env or gh auth token)
    has_token = bool(
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    if not has_token:
        try:
            token_result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            cli_token = (
                (token_result.stdout or "").strip()
                if token_result.returncode == 0
                else ""
            )
            if cli_token:
                os.environ.setdefault("GH_TOKEN", cli_token)
                has_token = True
        except Exception:
            has_token = False

    if has_token:
        checks.append(("GitHub Models token (env/gh auth)", "✅"))
    else:
        checks.append(
            (
                "GitHub Models token (env/gh auth)",
                "❌ Missing - run `gh auth login` or export GITHUB_TOKEN/GH_TOKEN",
            )
        )

    # Check Python virtual environment
    if Path(".venv").exists():
        checks.append(("Python virtualenv (.venv)", "✅"))
    else:
        checks.append(("Python virtualenv (.venv)", "❌ Run ./setup.sh to create"))

    # Check Node/npm if frontend or standalone client repo exists
    project_root = Path(__file__).resolve().parent.parent
    client_repo = project_root.parent / "softwareFactoryVscode"
    frontend_repo = client_repo / "client"
    if frontend_repo.exists():
        if shutil.which("node"):
            checks.append(("Node.js", "✅"))
        else:
            checks.append(("Node.js", "❌ Not found"))

        if shutil.which("npm"):
            checks.append(("npm", "✅"))
        else:
            checks.append(("npm", "❌ Not found"))

    # Print results
    print("Prerequisites:")
    for name, status in checks:
        print(f"  {name:.<40} {status}")
    print()

    # Return True if all checks passed
    return all("✅" in status for _, status in checks)


def _ensure_venv_and_reexec() -> None:
    """Ensure .venv exists and re-exec this script under the .venv interpreter.

    This keeps agent runs reproducible and guarantees Python 3.12 for this repo.
    """
    project_root = Path(__file__).parent.parent
    venv_python = project_root / ".venv" / "bin" / "python"
    venv_dir = project_root / ".venv"

    # Avoid infinite loops
    if os.environ.get("WORK_ISSUE_REEXEC") == "1":
        return

    # If venv is missing, bootstrap it
    if not venv_python.exists():
        setup_script = project_root / "setup.sh"
        if not setup_script.exists():
            return

        print("⚙️  .venv not found. Bootstrapping environment via ./setup.sh ...")
        import subprocess

        result = subprocess.run(["bash", str(setup_script)], cwd=str(project_root))
        if result.returncode != 0:
            print("❌ setup.sh failed; cannot continue.")
            sys.exit(result.returncode)

    # If we're not already running inside the venv, re-exec
    in_venv = False
    try:
        # VIRTUAL_ENV is the most reliable indicator.
        if os.environ.get("VIRTUAL_ENV"):
            in_venv = Path(os.environ["VIRTUAL_ENV"]).resolve() == venv_dir.resolve()
        else:
            # Fallback: sys.prefix points at venv when active.
            in_venv = Path(sys.prefix).resolve() == venv_dir.resolve()
    except Exception:
        in_venv = False

    if not in_venv and venv_python.exists():
        print(f"🔁 Re-executing under .venv Python: {venv_python}")
        os.environ["WORK_ISSUE_REEXEC"] = "1"
        os.execv(
            str(venv_python),
            [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        )


def _ensure_github_models_token() -> None:
    """Populate GH_TOKEN from gh auth when not already set.

    This prevents runtime initialization failures when users are already
    authenticated via GitHub CLI but have not exported token environment vars.
    """
    if (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    ):
        return

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        token = (result.stdout or "").strip() if result.returncode == 0 else ""
        if token:
            os.environ.setdefault("GH_TOKEN", token)
    except Exception:
        pass


def _archive_goals(stage: str, issue_number: int) -> None:
    """Archive Goal sections from .tmp markdown files.

    Non-fatal: failures only emit a warning.
    """
    project_root = Path(__file__).parent.parent
    tmp_path = project_root / ".copilot/softwareFactoryVscode/.tmp"
    tmp_path.mkdir(parents=True, exist_ok=True)
    
    script_path = project_root / "scripts" / "archive-goals.sh"

    if not script_path.exists():
        print(f"⚠️  Goal archive script not found: {script_path}")
        return

    try:
        print(f"🗄️  Goal archive ({stage}) for issue #{issue_number} ...")
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(project_root),
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"   {line}")
        else:
            print(
                f"⚠️  Goal archive ({stage}) failed with exit code {result.returncode}"
            )
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip())
    except Exception as exc:
        print(f"⚠️  Goal archive ({stage}) error: {exc}")


def _ensure_dev_stack(mode: str) -> bool:
    """Ensure backend API and frontend dev server are available for issue work."""
    if mode == "off":
        print("🧩 Dev stack check: OFF (skipped by --dev-stack off)")
        return True

    project_root = Path(__file__).parent.parent
    backend_health_url = os.environ.get(
        "WORK_ISSUE_BACKEND_HEALTH_URL", "http://127.0.0.1:8000/health"
    )
    frontend_url = os.environ.get("WORK_ISSUE_FRONTEND_URL", "http://127.0.0.1:5173")

    print("🧩 Ensuring dev stack (backend + frontend) ...")

    backend_ready = _is_url_ready(backend_health_url)
    frontend_ready = _is_url_ready(frontend_url)

    if not backend_ready or not frontend_ready:
        print("  🚀 Starting supervised dev stack (backend + frontend) ...")
        _start_dev_stack_supervisor(project_root)
        if not backend_ready:
            backend_ready = _wait_for_url(backend_health_url, timeout_seconds=45)
        if not frontend_ready:
            frontend_ready = _wait_for_url(frontend_url, timeout_seconds=90)

    print(
        f"  Backend: {'✅ ready' if backend_ready else '❌ not ready'} ({backend_health_url})"
    )
    print(
        f"  Frontend: {'✅ ready' if frontend_ready else '❌ not ready'} ({frontend_url})"
    )

    if backend_ready and frontend_ready:
        return True

    if mode == "required":
        return False

    print(
        "⚠️  Continuing with partial dev stack (mode=auto). "
        "Set --dev-stack required to enforce strict startup."
    )
    return False


def _is_url_ready(url: str, timeout_seconds: float = 2.0) -> bool:
    """Return True when an HTTP endpoint responds with 2xx/3xx/4xx quickly."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 500
    except Exception:
        return False


def _wait_for_url(
    url: str, timeout_seconds: int = 30, poll_seconds: float = 1.0
) -> bool:
    """Wait until URL responds or timeout is reached."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_url_ready(url):
            return True
        time.sleep(poll_seconds)
    return False


def _start_dev_stack_supervisor(project_root: Path) -> None:
    """Start dev stack supervisor in background if not already running."""
    logs_dir = project_root / ".copilot/softwareFactoryVscode/.tmp"
    logs_dir.mkdir(parents=True, exist_ok=True)

    pid_file = logs_dir / "dev-stack-supervisor.pid"
    if pid_file.exists():
        pid_text = pid_file.read_text(encoding="utf-8").strip()
        if pid_text.isdigit():
            try:
                os.kill(int(pid_text), 0)
                return
            except OSError:
                pid_file.unlink(missing_ok=True)

    supervisor_script = project_root / "scripts" / "dev_stack_supervisor.py"
    venv_python = project_root / ".venv" / "bin" / "python"
    log_path = logs_dir / "work-issue-dev-supervisor.log"

    with open(log_path, "a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [str(venv_python), str(supervisor_script)],
            cwd=str(project_root),
            env=dict(os.environ),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )


async def _interactive_mode(agent):
    """Run interactive mode for follow-up instructions."""
    print("\n" + "=" * 70)
    print("💬 Interactive Mode - Give additional instructions to the agent")
    print("   Type 'exit' or 'quit' to finish")
    print("=" * 70)
    print()

    while True:
        try:
            user_input = input("\n You: ").strip()

            if not user_input or user_input.lower() in ["exit", "quit", "q"]:
                break

            print("Agent: ", end="", flush=True)
            response = await agent.continue_conversation(user_input)
            print(response)

        except (KeyboardInterrupt, EOFError):
            break

    print("\n👋 Ending interactive session")


if __name__ == "__main__":
    asyncio.run(main())
