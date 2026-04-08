"""FACTORY CLI — run the orchestrator from the command line.

Usage:
    python -m agents.factory_cli --issue 42 --repo YOUR_ORG/YOUR_REPO

Or import and call directly:
    python agents/factory_cli.py --issue 42 --repo YOUR_ORG/YOUR_REPO

Implements: GitHub issue #715
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factory",
        description="FACTORY: AI agent pipeline for GitHub issue implementation",
    )
    parser.add_argument(
        "--issue",
        "-i",
        type=int,
        required=True,
        help="GitHub issue number to implement",
    )
    parser.add_argument(
        "--repo",
        "-r",
        required=True,
        help="Repository in owner/name format (e.g. YOUR_ORG/YOUR_REPO)",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Issue title (optional, used for PR title)",
    )
    parser.add_argument(
        "--body",
        default="",
        help="Issue body text (mutually exclusive with --body-file)",
    )
    parser.add_argument(
        "--body-file",
        default="",
        help="Path to a file containing the issue body",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Known relevant file paths for complexity scoring",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root path (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--kill-mcps-on-exit",
        action="store_true",
        help="Force the teardown of the MCP Docker network as the process terminates",
    )
    parser.add_argument(
        "--force-rebuild-mcps",
        action="store_true",
        help="Forcefully purge and rebuild the MCP mesh containers on startup",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    from factory_runtime.agents.factory import FactoryOrchestrator
    from factory_runtime.agents.mcp_lifecycle import MCPBootloader

    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text()

    workspace_root = Path(args.workspace).resolve()

    bootloader = MCPBootloader(
        workspace_root=workspace_root,
        kill_mcps_on_exit=args.kill_mcps_on_exit,
        force_rebuild_mcps=args.force_rebuild_mcps,
    )
    bootloader.setup_signal_handlers()
    await bootloader.initialize()

    try:
        orq = FactoryOrchestrator(workspace_root=workspace_root)
        result = await orq.run_issue(
            issue_number=args.issue,
            repo=args.repo,
            issue_title=args.title,
            issue_body=body,
            changed_files=args.files,
        )

        if args.output_json:
            print(
                json.dumps(
                    {
                        "issue_number": result.issue_number,
                        "repo": result.repo,
                        "run_id": result.run_id,
                        "pr_url": result.pr_url,
                        "files_changed": result.files_changed,
                        "complexity_score": result.complexity_score,
                        "model_tier": result.model_tier,
                        "tests_passed": result.tests_passed,
                        "error": result.error,
                        "success": result.success,
                    },
                    indent=2,
                )
            )
        else:
            _print_result(result)

        return 0 if result.success else 1
    finally:
        bootloader.teardown()


def _print_result(result) -> None:
    """Human-readable result output."""
    icon = "✅" if result.success else "❌"
    print(f"\n{icon} FACTORY run complete for issue #{result.issue_number}")
    print(f"   Repo:       {result.repo}")
    print(f"   Run ID:     {result.run_id or 'N/A'}")
    print(f"   Complexity: {result.complexity_score} ({result.model_tier})")
    print(f"   Tests:      {'PASSED' if result.tests_passed else 'FAILED'}")

    if result.files_changed:
        print(f"   Files ({len(result.files_changed)}):")
        for f in result.files_changed:
            print(f"     - {f}")

    if result.pr_url:
        print(f"   PR:         {result.pr_url}")

    if result.error:
        print(f"   Error:      {result.error}", file=sys.stderr)


def _run_queue_loop(poll_interval_seconds: float = 5.0) -> int:
    """Run a lightweight queue-worker loop for containerized agent-worker mode."""
    print("🏭 agent-worker queue loop started")
    try:
        while True:
            time.sleep(poll_interval_seconds)
    except KeyboardInterrupt:
        print("\n🛑 agent-worker queue loop interrupted")
    return 0


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "run-queue":
        sys.exit(_run_queue_loop())

    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
