from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .audit_store import AuditRecord, AuditStore, redact_secrets
from .policy import GitHubOpsPolicy


class GitHubOpsServiceError(RuntimeError):
    """Raised when a GitHub Ops command fails."""


CheckConclusion = Literal[
    "SUCCESS",
    "FAILURE",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "SKIPPED",
    "NEUTRAL",
]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize_checks(status_rollup: list[dict[str, Any]] | None) -> dict[str, Any]:
    items = status_rollup or []
    conclusions: list[str] = []
    pending = 0

    for it in items:
        conclusion = it.get("conclusion")
        if conclusion is None:
            pending += 1
        else:
            conclusions.append(str(conclusion).upper())

    uniq = sorted(set(conclusions))
    has_failure = any(
        c in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for c in uniq
    )
    has_success = "SUCCESS" in uniq
    all_success = len(uniq) == 1 and uniq[0] == "SUCCESS" and pending == 0

    return {
        "conclusions": uniq,
        "pending": pending,
        "all_success": all_success,
        "has_failure": has_failure,
        "has_success": has_success,
        "count": len(items),
    }


@dataclass
class GitHubOpsService:
    repo_root: Path
    policy: GitHubOpsPolicy
    audit_dir: Path
    gh_bin: str = "gh"

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.audit_store = AuditStore(self.audit_dir)

    def _run(
        self,
        *,
        tool: str,
        command: list[str],
        timeout_sec: int = 60,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        started_at = _now_utc_iso()
        start = time.perf_counter()

        if dry_run:
            output = f"DRY-RUN: {' '.join(command)}"
            duration = time.perf_counter() - start
            record = AuditRecord(
                run_id=run_id,
                tool=tool,
                timestamp_utc=started_at,
                status="simulated",
                exit_code=0,
                duration_sec=duration,
                cwd=str(self.repo_root),
                command=command,
                output=output,
            )
            self.audit_store.save(record)
            return {
                "run_id": run_id,
                "status": "simulated",
                "exit_code": 0,
                "duration_sec": duration,
                "output": output,
                "command": command,
            }

        try:
            proc = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            output = redact_secrets(output)
            duration = time.perf_counter() - start
            record = AuditRecord(
                run_id=run_id,
                tool=tool,
                timestamp_utc=started_at,
                status="timeout",
                exit_code=124,
                duration_sec=duration,
                cwd=str(self.repo_root),
                command=command,
                output=output,
            )
            self.audit_store.save(record)
            raise GitHubOpsServiceError(output or "Command timed out") from exc

        output = "\n".join(
            chunk for chunk in (proc.stdout.strip(), proc.stderr.strip()) if chunk
        )
        output = redact_secrets(output)

        status = "ok" if proc.returncode == 0 else "error"
        duration = time.perf_counter() - start

        record = AuditRecord(
            run_id=run_id,
            tool=tool,
            timestamp_utc=started_at,
            status=status,
            exit_code=int(proc.returncode),
            duration_sec=duration,
            cwd=str(self.repo_root),
            command=command,
            output=output,
        )
        self.audit_store.save(record)

        if proc.returncode != 0:
            raise GitHubOpsServiceError(
                output or f"Command failed: {' '.join(command)}"
            )

        return {
            "run_id": run_id,
            "status": status,
            "exit_code": int(proc.returncode),
            "duration_sec": duration,
            "output": output,
        }

    def _run_json(
        self,
        *,
        tool: str,
        command: list[str],
        timeout_sec: int = 60,
    ) -> dict[str, Any]:
        result = self._run(tool=tool, command=command, timeout_sec=timeout_sec)
        raw = (result.get("output") or "").strip()
        if not raw:
            return {"run_id": result.get("run_id"), "data": None}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubOpsServiceError(
                f"Expected JSON output, got: {raw[:400]}"
            ) from exc
        return {"run_id": result.get("run_id"), "data": data}

    def repos_allowed(self) -> dict[str, Any]:
        return {"allowed_repos": sorted(self.policy.allowed_repos)}

    def issue_view(self, *, repo: str, issue_number: int) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        payload = self._run_json(
            tool="issue_view",
            command=[
                self.gh_bin,
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repo,
                "--json",
                "number,title,state,url,labels,closedAt",
            ],
        )
        data = payload["data"]
        return {"run_id": payload["run_id"], "issue": data}

    def issue_exists(self, *, repo: str, issue_number: int) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        try:
            result = self.issue_view(repo=repo, issue_number=issue_number)
        except GitHubOpsServiceError:
            return {"exists": False}

        issue = result.get("issue") or {}
        return {"exists": True, "state": issue.get("state"), "url": issue.get("url")}

    def pr_view(self, *, repo: str, pr_number: int) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        payload = self._run_json(
            tool="pr_view",
            command=[
                self.gh_bin,
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "number,title,state,url,headRefName,isDraft,mergeable,mergeStateStatus,reviewDecision,body,mergeCommit,statusCheckRollup",
            ],
        )
        return {"run_id": payload["run_id"], "pr": payload["data"]}

    def pr_body(self, *, repo: str, pr_number: int) -> dict[str, Any]:
        pr = self.pr_view(repo=repo, pr_number=pr_number)
        return {"run_id": pr["run_id"], "body": (pr.get("pr") or {}).get("body") or ""}

    def pr_files(self, *, repo: str, pr_number: int) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        payload = self._run_json(
            tool="pr_files",
            command=[
                self.gh_bin,
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "files,additions,deletions,changedFiles",
            ],
        )
        pr = payload["data"] or {}
        files = pr.get("files") or []
        totals = {
            "files": int(pr.get("changedFiles") or len(files)),
            "additions": int(pr.get("additions") or 0),
            "deletions": int(pr.get("deletions") or 0),
        }
        return {"run_id": payload["run_id"], "files": files, "totals": totals}

    def pr_checks_summary(self, *, repo: str, pr_number: int) -> dict[str, Any]:
        pr = self.pr_view(repo=repo, pr_number=pr_number)
        status_rollup = (pr.get("pr") or {}).get("statusCheckRollup")
        summary = _summarize_checks(
            status_rollup if isinstance(status_rollup, list) else None
        )
        return {
            "run_id": pr["run_id"],
            "summary": summary,
            "checks": status_rollup or [],
        }

    def pr_checks_watch(
        self,
        *,
        repo: str,
        pr_number: int,
        timeout_sec: int = 1200,
        interval_sec: int = 15,
        fail_fast: bool = True,
    ) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        if timeout_sec <= 0:
            raise ValueError("timeout_sec must be > 0")
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")

        deadline = time.time() + timeout_sec
        last: dict[str, Any] | None = None

        while time.time() < deadline:
            last = self.pr_checks_summary(repo=repo, pr_number=pr_number)
            summary = last.get("summary") or {}

            if summary.get("all_success"):
                return {"status": "success", **last}

            if fail_fast and summary.get("has_failure"):
                return {"status": "failure", **last}

            time.sleep(interval_sec)

        return {"status": "timeout", **(last or {})}

    def workflow_runs_list(
        self,
        *,
        repo: str,
        branch: str,
        status: str = "in_progress",
        limit: int = 50,
    ) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        if limit <= 0 or limit > 200:
            raise ValueError("limit must be between 1 and 200")

        payload = self._run_json(
            tool="workflow_runs_list",
            command=[
                self.gh_bin,
                "run",
                "list",
                "--repo",
                repo,
                "--branch",
                branch,
                "--status",
                status,
                "--limit",
                str(limit),
                "--json",
                "databaseId,workflowName,createdAt,url",
            ],
        )
        runs = payload["data"] or []
        return {"run_id": payload["run_id"], "runs": runs, "count": len(runs)}

    def workflow_run_cancel(
        self,
        *,
        repo: str,
        run_id: int,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        return self._run(
            tool="workflow_run_cancel",
            command=[
                self.gh_bin,
                "run",
                "cancel",
                str(run_id),
                "--repo",
                repo,
            ],
            timeout_sec=60,
            dry_run=dry_run,
        )

    def pr_merge_squash(
        self,
        *,
        repo: str,
        pr_number: int,
        delete_branch: bool = True,
        admin: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)

        command = [
            self.gh_bin,
            "pr",
            "merge",
            str(pr_number),
            "--repo",
            repo,
            "--squash",
        ]
        if delete_branch:
            command.append("--delete-branch")
        if admin:
            command.append("--admin")

        merge_result = self._run(
            tool="pr_merge_squash",
            command=command,
            timeout_sec=1800,
            dry_run=dry_run,
        )

        if dry_run:
            return {"merged": False, **merge_result}

        # Best-effort: fetch merge commit SHA after merge.
        merge_commit_sha: str | None = None
        for _ in range(10):
            try:
                view = self.pr_view(repo=repo, pr_number=pr_number)
                mc = (view.get("pr") or {}).get("mergeCommit") or {}
                merge_commit_sha = mc.get("oid") or mc.get("sha")
                if merge_commit_sha:
                    break
            except GitHubOpsServiceError:
                pass
            time.sleep(2)

        return {
            "merged": True,
            "merge_commit_sha": merge_commit_sha,
            **merge_result,
        }

    def issue_close(
        self,
        *,
        repo: str,
        issue_number: int,
        comment: str,
        reason: str = "completed",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        repo = self.policy.validate_repo(repo)
        if not comment.strip():
            raise ValueError("comment must be non-empty")

        return self._run(
            tool="issue_close",
            command=[
                self.gh_bin,
                "issue",
                "close",
                str(issue_number),
                "--repo",
                repo,
                "--reason",
                reason,
                "--comment",
                comment,
            ],
            timeout_sec=120,
            dry_run=dry_run,
        )

    def pr_find_for_issue(
        self,
        *,
        issue_number: int,
        repos: list[str],
        prefer_state: Literal["open", "merged", "all"] = "open",
        limit: int = 30,
    ) -> dict[str, Any]:
        if issue_number <= 0:
            raise ValueError("issue_number must be > 0")

        pattern = re.compile(r"\[(?:issue\s*)?#?(\d+)\]|#(\d+)", re.IGNORECASE)

        best: dict[str, Any] | None = None

        for repo in repos:
            repo = self.policy.validate_repo(repo)

            state_arg = prefer_state if prefer_state in {"open", "merged"} else "all"
            payload = self._run_json(
                tool="pr_find_for_issue",
                command=[
                    self.gh_bin,
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    state_arg,
                    "--limit",
                    str(limit),
                    "--search",
                    str(issue_number),
                    "--json",
                    "number,title,state,url,headRefName",
                ],
                timeout_sec=60,
            )

            prs = payload["data"] or []
            for pr in prs:
                title = str(pr.get("title") or "")
                match = pattern.search(title)
                if not match:
                    continue
                matched = int(match.group(1) or match.group(2) or 0)
                if matched != issue_number:
                    continue

                candidate = {
                    "repo": repo,
                    "pr_number": int(pr.get("number")),
                    "url": pr.get("url"),
                    "title": title,
                    "state": pr.get("state"),
                    "matched_by": "title_search",
                    "confidence": 0.8,
                }
                best = candidate
                break

            if best:
                break

        return {"match": best, "found": bool(best)}

    def get_run_log(self, run_id: str) -> dict[str, Any] | None:
        return self.audit_store.get(run_id)


def load_default_policy() -> GitHubOpsPolicy:
    return GitHubOpsPolicy.from_env(
        allowed_repos_env=os.getenv("GITHUB_OPS_ALLOWED_REPOS"),
        default_allowed_repos=[
            "YOUR_ORG/YOUR_REPO",
        ],
    )
