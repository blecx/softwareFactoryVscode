#!/usr/bin/env python3
"""Recommend the next PR to merge (PR-first workflow).

This helper scans open PRs across:
- YOUR_ORG/YOUR_REPO (backend)
- ${CLIENT_REPO} (client)

It ranks PRs by merge readiness (CI success, mergeable, clean merge state, not draft)
so the pr-merge workflow can stay PR-focused.

Usage:
  ./scripts/next-pr.py
  ./scripts/next-pr.py --repo backend|client|both
  ./scripts/next-pr.py --limit 20
  ./scripts/next-pr.py --json

Environment:
    NEXT_PR_GH_MIN_INTERVAL   Minimum seconds between gh requests (default: 1.0)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


RepoKey = Literal["backend", "client"]


REPOS: dict[RepoKey, str] = {
    "backend": os.environ.get("TARGET_REPO", "YOUR_ORG/YOUR_REPO"),
    "client": os.environ.get("CLIENT_REPO", os.environ.get("CLIENT_REPO", "YOUR_ORG/YOUR_CLIENT_REPO")),
}

DEFAULT_GH_MIN_INTERVAL_SECONDS = 1.0
_GH_LAST_REQUEST_TS: float | None = None


@dataclass(frozen=True)
class PrCandidate:
    repo_key: RepoKey
    repo: str
    number: int
    title: str
    url: str
    head_ref: str
    updated_at: str
    is_draft: bool
    mergeable: str
    merge_state_status: str
    review_decision: str
    checks_summary: dict[str, Any]
    score: int


def _run_gh_json(args: list[str]) -> Any:
    _throttle_gh_requests()
    cmd = ["gh", *args]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.output.decode("utf-8", errors="replace")) from e

    raw = out.decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    return json.loads(raw)


def _throttle_gh_requests() -> None:
    global _GH_LAST_REQUEST_TS

    min_interval = max(
        0.0,
        float(os.getenv("NEXT_PR_GH_MIN_INTERVAL", str(DEFAULT_GH_MIN_INTERVAL_SECONDS))),
    )
    if min_interval <= 0:
        _GH_LAST_REQUEST_TS = time.monotonic()
        return

    now = time.monotonic()
    if _GH_LAST_REQUEST_TS is not None:
        elapsed = now - _GH_LAST_REQUEST_TS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    _GH_LAST_REQUEST_TS = time.monotonic()


def _parse_iso(ts: str) -> datetime:
    # GitHub returns ISO8601 like 2026-01-25T21:16:23Z
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _summarize_checks(status_rollup: list[dict[str, Any]] | None) -> dict[str, Any]:
    items = status_rollup or []
    conclusions: list[str] = []
    pending = 0
    for it in items:
        concl = it.get("conclusion")
        if concl is None:
            pending += 1
        else:
            conclusions.append(str(concl).upper())

    uniq = sorted(set(conclusions))
    has_failure = any(c in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for c in uniq)
    has_success = "SUCCESS" in uniq

    all_success = (len(uniq) == 1 and uniq[0] == "SUCCESS" and pending == 0)

    return {
        "conclusions": uniq,
        "pending": pending,
        "all_success": all_success,
        "has_failure": has_failure,
        "has_success": has_success,
        "count": len(items),
    }


def _score_pr(*, is_draft: bool, mergeable: str, merge_state_status: str, checks: dict[str, Any], review_decision: str) -> int:
    score = 0

    if is_draft:
        score -= 20
    else:
        score += 5

    if mergeable.upper() == "MERGEABLE":
        score += 5
    elif mergeable.upper() == "CONFLICTING":
        score -= 10
    else:
        score -= 2

    mss = merge_state_status.upper()
    if mss == "CLEAN":
        score += 8
    elif mss == "UNSTABLE":
        score += 1
    elif mss in {"BLOCKED", "DIRTY"}:
        score -= 5

    if checks.get("all_success"):
        score += 15
    elif checks.get("has_failure"):
        score -= 15
    else:
        # Pending/unknown
        score += 0

    rd = (review_decision or "").upper()
    if rd == "APPROVED":
        score += 3
    elif rd == "CHANGES_REQUESTED":
        score -= 3

    return score


def _fetch_open_prs(repo: str, limit: int) -> list[dict[str, Any]]:
    return _run_gh_json(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,url,updatedAt,isDraft,headRefName",
        ]
    )


def _fetch_pr_details(repo: str, number: int) -> dict[str, Any]:
    return _run_gh_json(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "mergeable,mergeStateStatus,statusCheckRollup,reviewDecision",
        ]
    )


def recommend(repo_filter: Literal["backend", "client", "both"], limit: int) -> list[PrCandidate]:
    repo_keys: list[RepoKey]
    if repo_filter == "both":
        repo_keys = ["client", "backend"]
    else:
        repo_keys = [repo_filter]

    candidates: list[PrCandidate] = []

    for repo_key in repo_keys:
        repo = REPOS[repo_key]
        prs = _fetch_open_prs(repo, limit)
        for pr in prs:
            number = int(pr["number"])
            details = _fetch_pr_details(repo, number)
            checks = _summarize_checks(details.get("statusCheckRollup"))
            score = _score_pr(
                is_draft=bool(pr.get("isDraft")),
                mergeable=str(details.get("mergeable") or ""),
                merge_state_status=str(details.get("mergeStateStatus") or ""),
                checks=checks,
                review_decision=str(details.get("reviewDecision") or ""),
            )
            candidates.append(
                PrCandidate(
                    repo_key=repo_key,
                    repo=repo,
                    number=number,
                    title=str(pr.get("title") or ""),
                    url=str(pr.get("url") or ""),
                    head_ref=str(pr.get("headRefName") or ""),
                    updated_at=str(pr.get("updatedAt") or ""),
                    is_draft=bool(pr.get("isDraft")),
                    mergeable=str(details.get("mergeable") or ""),
                    merge_state_status=str(details.get("mergeStateStatus") or ""),
                    review_decision=str(details.get("reviewDecision") or ""),
                    checks_summary=checks,
                    score=score,
                )
            )

    candidates.sort(key=lambda c: (c.score, _parse_iso(c.updated_at)), reverse=True)
    return candidates


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Recommend the next PR to merge (PR-first)")
    parser.add_argument("--repo", choices=["backend", "client", "both"], default="both")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        candidates = recommend(args.repo, args.limit)
    except RuntimeError as e:
        print("ERROR: failed to query GitHub via gh CLI", file=sys.stderr)
        print(str(e).strip(), file=sys.stderr)
        return 2

    if args.json:
        payload = [
            {
                "repo": c.repo,
                "repo_key": c.repo_key,
                "number": c.number,
                "title": c.title,
                "url": c.url,
                "head_ref": c.head_ref,
                "updated_at": c.updated_at,
                "is_draft": c.is_draft,
                "mergeable": c.mergeable,
                "merge_state_status": c.merge_state_status,
                "review_decision": c.review_decision,
                "checks": c.checks_summary,
                "score": c.score,
            }
            for c in candidates
        ]
        print(json.dumps({"recommended": payload[:1], "candidates": payload}, indent=2))
        return 0

    print("================================================================================")
    print("NEXT PR RECOMMENDATION")
    print("================================================================================")

    if not candidates:
        print("No open PRs found.")
        return 0

    top = candidates[0]
    print(f"Selected PR: #{top.number} ({top.repo})")
    print(f"Title: {top.title}")
    print(f"URL: {top.url}")
    print(f"Draft: {top.is_draft}")
    print(f"Mergeable: {top.mergeable} | Merge state: {top.merge_state_status}")
    print(
        f"Checks: {top.checks_summary.get('conclusions')}"
        f" (pending={top.checks_summary.get('pending')}, all_success={top.checks_summary.get('all_success')})"
    )
    print(f"Score: {top.score}")
    print("--------------------------------------------------------------------------------")
    print("Top candidates:")

    for c in candidates[: min(10, len(candidates))]:
        checks = c.checks_summary
        concl = ",".join(checks.get("conclusions") or []) or "(none)"
        pending = checks.get("pending")
        print(
            f"- {c.repo_key:7} #{c.number:<4} score={c.score:<3} mss={c.merge_state_status:<9} "
            f"mergeable={c.mergeable:<11} draft={str(c.is_draft):<5} checks={concl} pending={pending}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
