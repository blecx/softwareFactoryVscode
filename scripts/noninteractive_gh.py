#!/usr/bin/env python3
"""Pager-free, machine-friendly GitHub CLI helper for repo automation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_runtime.agents.tooling.gh_throttle import run_gh_throttled

ISSUE_LIST_FIELDS = "number,title,state,url,labels,updatedAt"
ISSUE_VIEW_FIELDS = "number,title,state,url,closedAt"
PR_VIEW_FIELDS = "number,title,state,isDraft,mergeable,reviewDecision,url,headRefName,baseRefName,mergedAt"
PR_CHECK_FIELDS = "number,title,url,statusCheckRollup"
REPO_VIEW_FIELDS = "nameWithOwner,url,defaultBranchRef"
COMPLETED_FAILURES = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "FAILURE",
    "STALE",
    "STARTUP_FAILURE",
    "TIMED_OUT",
}


def build_noninteractive_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GH_PAGER"] = "cat"
    env["PAGER"] = "cat"
    env.setdefault("LESS", "FRX")
    return env


def run_gh_json(args: Sequence[str]) -> Any:
    result = run_gh_throttled(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        env=build_noninteractive_env(),
    )
    if result.returncode != 0:
        output = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
        raise RuntimeError(
            output or f"gh command failed with exit code {result.returncode}"
        )

    raw = (result.stdout or "").strip()
    return json.loads(raw) if raw else None


def build_query_metadata(
    kind: str, *, selector: str = "", repo: str = ""
) -> dict[str, Any]:
    return {
        "kind": kind,
        "selector": selector,
        "repo": repo,
        "pager_disabled": True,
        "watch_mode": False,
    }


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    labels = issue.get("labels") or []
    return {
        **issue,
        "labelNames": [
            str(label.get("name", "")).strip()
            for label in labels
            if isinstance(label, dict) and str(label.get("name", "")).strip()
        ],
    }


def summarize_status_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "overall": "no-checks",
        "total": len(checks),
        "successful": 0,
        "pending": 0,
        "failing": 0,
        "cancelled": 0,
        "skipped": 0,
        "other": 0,
    }

    for check in checks:
        status = str(check.get("status", "")).upper()
        conclusion = str(check.get("conclusion", "")).upper()

        if status != "COMPLETED" or not conclusion:
            summary["pending"] += 1
            continue

        if conclusion == "SUCCESS":
            summary["successful"] += 1
        elif conclusion == "CANCELLED":
            summary["cancelled"] += 1
        elif conclusion == "SKIPPED":
            summary["skipped"] += 1
        elif conclusion in COMPLETED_FAILURES:
            summary["failing"] += 1
        else:
            summary["other"] += 1

    if summary["failing"]:
        summary["overall"] = "failure"
    elif summary["pending"]:
        summary["overall"] = "pending"
    elif summary["total"] and summary["successful"] == summary["total"]:
        summary["overall"] = "success"
    elif summary["total"]:
        summary["overall"] = "mixed"

    return summary


def normalize_status_check(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(item.get("__typename", "")),
        "name": str(item.get("name", "")),
        "workflow": str(item.get("workflowName", "")),
        "status": str(item.get("status", "")),
        "conclusion": str(item.get("conclusion", "")),
        "startedAt": item.get("startedAt"),
        "completedAt": item.get("completedAt"),
        "detailsUrl": str(item.get("detailsUrl", "")),
    }


def build_issue_list_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        "issue",
        "list",
        "--state",
        args.state,
        "--limit",
        str(args.limit),
        "--json",
        ISSUE_LIST_FIELDS,
    ]
    if args.repo:
        command.extend(["--repo", args.repo])
    if args.search:
        command.extend(["--search", args.search])

    issues = run_gh_json(command) or []
    return {
        "query": build_query_metadata("issue-list", repo=args.repo),
        "issues": [normalize_issue(issue) for issue in issues],
    }


def build_issue_view_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = ["issue", "view", args.selector, "--json", ISSUE_VIEW_FIELDS]
    if args.repo:
        command.extend(["--repo", args.repo])

    issue = run_gh_json(command) or {}
    return {
        "query": build_query_metadata(
            "issue-view",
            selector=args.selector,
            repo=args.repo,
        ),
        "issue": normalize_issue(issue),
    }


def build_pr_view_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = ["pr", "view", args.selector, "--json", PR_VIEW_FIELDS]
    if args.repo:
        command.extend(["--repo", args.repo])

    pr = run_gh_json(command) or {}
    return {
        "query": build_query_metadata(
            "pr-view",
            selector=args.selector,
            repo=args.repo,
        ),
        "pr": pr,
    }


def build_pr_checks_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = ["pr", "view", args.selector, "--json", PR_CHECK_FIELDS]
    if args.repo:
        command.extend(["--repo", args.repo])

    pr = run_gh_json(command) or {}
    checks = [
        normalize_status_check(item)
        for item in (pr.get("statusCheckRollup") or [])
        if isinstance(item, dict)
    ]
    return {
        "query": build_query_metadata(
            "pr-checks",
            selector=args.selector,
            repo=args.repo,
        ),
        "pr": {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("url"),
        },
        "summary": summarize_status_checks(checks),
        "checks": checks,
    }


def build_repo_view_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = ["repo", "view", "--json", REPO_VIEW_FIELDS]
    if args.repo:
        command.extend(["--repo", args.repo])

    repo = run_gh_json(command) or {}
    return {
        "query": build_query_metadata("repo-view", repo=args.repo),
        "repo": repo,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run GitHub CLI status queries in a pager-free, machine-friendly way."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    issue_list = subparsers.add_parser("issue-list")
    issue_list.add_argument("--repo", default="")
    issue_list.add_argument("--state", default="open")
    issue_list.add_argument("--limit", type=int, default=50)
    issue_list.add_argument("--search", default="")
    issue_list.set_defaults(handler=build_issue_list_payload)

    issue_view = subparsers.add_parser("issue-view")
    issue_view.add_argument("selector")
    issue_view.add_argument("--repo", default="")
    issue_view.set_defaults(handler=build_issue_view_payload)

    pr_view = subparsers.add_parser("pr-view")
    pr_view.add_argument("selector")
    pr_view.add_argument("--repo", default="")
    pr_view.set_defaults(handler=build_pr_view_payload)

    pr_checks = subparsers.add_parser("pr-checks")
    pr_checks.add_argument("selector")
    pr_checks.add_argument("--repo", default="")
    pr_checks.set_defaults(handler=build_pr_checks_payload)

    repo_view = subparsers.add_parser("repo-view")
    repo_view.add_argument("--repo", default="")
    repo_view.set_defaults(handler=build_repo_view_payload)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
