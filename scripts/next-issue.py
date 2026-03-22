#!/usr/bin/env python3
"""
Next Issue Selector - Intelligent issue selection with reconciliation

WORKFLOW (in order):
1. RECONCILIATION PHASE (repeat until clean):
   - Check GitHub for merged PRs → close associated issues if not closed
   - Check closed PRs → verify issues are also closed on GitHub
   - Update local tracking documentation to match GitHub state
   - Commit and sync all changes
   - Repeat until everything is reconciled

2. SELECTION PHASE (only after reconciliation):
    - Query GitHub for open issues (source of truth)
    - Use tracking file ONLY for metadata (estimated hours, phase, blockers)
    - Select next issue based on priority, dependencies, and order
    - Never hardcode "next issue" in docs (GitHub is source of truth)

IMPORTANT: GitHub is the source of truth. Local markdown files are updated
to match GitHub state, never the other way around.

Usage:
    ./scripts/next-issue.py [--verbose] [--dry-run] [--skip-reconcile]

Environment:
    NEXT_ISSUE_GH_MIN_INTERVAL  Minimum seconds between GitHub CLI requests (default: 1.0)
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Repository root
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_runtime.agents.tooling.gh_throttle import run_gh_throttled

PLACEHOLDER_REPOS = {"YOUR_ORG/YOUR_REPO", "YOUR_ORG/YOUR_CLIENT_REPO"}


def _looks_like_placeholder_repo(repo: str) -> bool:
    return repo.strip() in PLACEHOLDER_REPOS


def _detect_current_repo() -> str:
    try:
        result = run_gh_throttled(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=5,
            min_interval_seconds=0,
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""

    return (result.stdout or "").strip()


def _resolve_github_repo() -> str:
    configured_repo = os.environ.get("TARGET_REPO", "YOUR_ORG/YOUR_REPO").strip()
    if not _looks_like_placeholder_repo(configured_repo):
        return configured_repo

    detected_repo = _detect_current_repo()
    if detected_repo:
        return detected_repo

    return configured_repo


def _resolve_step1_file(primary: Path, fallback: Path) -> Path:
    """Resolve the current location of Step-1 workflow files.

    The Step-1 tracking/status docs were moved under `planning/archive/`.
    Keep backward compatibility with older paths at repo root.
    """
    return primary if primary.exists() else fallback


TRACKING_FILE = _resolve_step1_file(
    REPO_ROOT / "STEP-1-IMPLEMENTATION-TRACKING.md",
    REPO_ROOT / "planning" / "archive" / "STEP-1-IMPLEMENTATION-TRACKING.md",
)
STATUS_FILE = _resolve_step1_file(
    REPO_ROOT / "STEP-1-STATUS.md",
    REPO_ROOT / "planning" / "archive" / "STEP-1-STATUS.md",
)
KNOWLEDGE_FILE = REPO_ROOT / ".issue-resolution-knowledge.json"

# GitHub repository
GITHUB_REPO = _resolve_github_repo()

# Configuration
DEFAULT_TIMEOUT = 15  # seconds for individual operations
MAX_RECONCILE_ITERATIONS = 3
STEP1_ISSUE_RANGE = (24, 59)  # Legacy Step-1 metadata window


class TimeoutError(Exception):
    """Raised when an operation times out"""

    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout"""
    raise TimeoutError("Operation timed out")


class ProgressIndicator:
    """Simple progress indicator for long operations"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.current = 0
        self.total = 0

    def start(self, total: int, message: str):
        """Start progress tracking"""
        self.current = 0
        self.total = total
        if not self.verbose:
            print(f"{message} (0/{total})", end="", flush=True)

    def update(self, increment: int = 1):
        """Update progress"""
        self.current += increment
        if not self.verbose and self.total > 0:
            print(f"\r{self.current}/{self.total}", end="", flush=True)

    def finish(self, message: str = ""):
        """Finish progress"""
        if not self.verbose:
            print(f"\r✓ {message}          ")


class Reconciler:
    """Reconciles GitHub state with local tracking documentation"""

    def __init__(
        self, github: "GitHubClient", tracking_file: Path, verbose: bool = False
    ):
        self.github = github
        self.tracking_file = tracking_file
        self.verbose = verbose
        self.changes_made = []
        self.progress = ProgressIndicator(verbose)

    def reconcile(self) -> bool:
        """
        Run full reconciliation cycle with timeout protection.
        Returns True if changes were made, False if everything is already in sync.
        """
        if self.verbose:
            print("\n" + "=" * 80, file=sys.stderr)
            print("RECONCILIATION PHASE", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
        else:
            print("🔄 Reconciling with GitHub...", flush=True)

        self.changes_made = []

        try:
            # Step 1: Check for merged PRs and close associated issues
            self._reconcile_merged_prs()

            # Step 2: Update local tracking to match GitHub (most important)
            if self.tracking_file.exists():
                self._update_tracking_file()
            elif self.verbose:
                print(
                    "\nℹ️  Tracking file not found; skipping local tracker reconciliation.",
                    file=sys.stderr,
                )
            else:
                print("ℹ️  No legacy tracking file found; using GitHub-only selection.")

            # Step 3: Commit and sync if changes were made
            if self.changes_made:
                self._commit_and_sync()
                return True

            if self.verbose:
                print("\n✅ All reconciled - no changes needed", file=sys.stderr)
            else:
                print("✅ Everything in sync")

            return False

        except TimeoutError:
            print(
                "\n⚠️  Reconciliation timed out. Partial results may be available.",
                file=sys.stderr,
            )
            return False
        except Exception as e:
            print(f"\n❌ Reconciliation error: {e}", file=sys.stderr)
            return False

    def _reconcile_merged_prs(self):
        """Check for merged PRs and ensure issues are closed"""
        if self.verbose:
            print("\n📋 Checking merged PRs...", file=sys.stderr)

        # Get all merged PRs (limited to recent ones)
        merged_prs = self.github._run_gh_command(
            [
                "pr",
                "list",
                "--state",
                "merged",
                "--limit",
                "20",
                "--json",
                "number,title,mergedAt,closedAt",
            ],
            timeout=20,
        )

        if not merged_prs:
            return

        for pr in merged_prs:
            # Extract issue number from PR title
            title = pr.get("title", "")
            issue_match = re.search(
                r"\[(?:issue )?#?(\d+)\]|#(\d+)", title, re.IGNORECASE
            )

            if issue_match:
                issue_num = int(issue_match.group(1) or issue_match.group(2))

                # Check if issue is closed
                if not self.github.is_issue_closed(issue_num):
                    if self.verbose:
                        print(
                            f"  ⚠️  PR #{pr['number']} is merged but Issue #{issue_num} is still open",
                            file=sys.stderr,
                        )

                    # Close the issue
                    self._close_issue(issue_num, pr["number"])

    def _reconcile_closed_prs(self):
        """Check closed PRs have closed issues - only check recent ones"""
        if self.verbose:
            print("\n📋 Verifying recently closed issues...", file=sys.stderr)

        # Check only Step 1 issues (24-58 as defined in tracking)
        # Only check ones that might be recently closed
        for issue_num in range(24, 35):  # Check first 11 issues for now
            if self.github.is_issue_closed(issue_num):
                # Check if there's a merged PR
                pr = self.github.get_merged_pr_for_issue(issue_num)

                if pr and self.verbose:
                    print(
                        f"  ✅ Issue #{issue_num} closed with PR #{pr['number']}",
                        file=sys.stderr,
                    )

    def _close_issue(self, issue_num: int, pr_number: int):
        """Close an issue on GitHub"""
        try:
            comment = f"Closing issue as PR #{pr_number} has been merged."

            result = subprocess.run(
                [
                    "gh",
                    "issue",
                    "close",
                    str(issue_num),
                    "--repo",
                    self.github.repo,
                    "--comment",
                    comment,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                self.changes_made.append(
                    f"Closed Issue #{issue_num} (PR #{pr_number} was merged)"
                )
                print(f"  ✅ Closed Issue #{issue_num}", file=sys.stderr)
            else:
                print(
                    f"  ❌ Failed to close Issue #{issue_num}: {result.stderr}",
                    file=sys.stderr,
                )

        except Exception as e:
            print(f"  ❌ Error closing Issue #{issue_num}: {e}", file=sys.stderr)

    def _update_tracking_file(self):
        """Update local tracking file to match GitHub state"""
        if not self.tracking_file.exists():
            return

        if self.verbose:
            print("\n📝 Updating local tracking file...", file=sys.stderr)

        # Get Step 1 issue numbers from tracking file (24-58, defined order)
        issue_numbers = list(range(24, 59))

        # Get their states from GitHub (query individually with timeout)
        github_states = {}
        for issue_num in issue_numbers:
            data = self.github._run_gh_command(
                ["issue", "view", str(issue_num), "--json", "number,state"], timeout=10
            )

            if data:
                github_states[issue_num] = data["state"]

        # Read current tracking file
        content = self.tracking_file.read_text()
        updated_content = content

        # Update each issue's status in tracking file
        for issue_num, github_state in github_states.items():
            # Find issue in tracking file with simpler, faster regex
            issue_pattern = rf"(### Issue #{issue_num}:.*?\n\*\*Status:\*\*\s+)([^\n]+)"
            match = re.search(issue_pattern, updated_content)

            if match:
                current_status = match.group(2).strip()

                # Determine correct status based on GitHub
                if github_state == "CLOSED":
                    # Check if we have a merged PR
                    pr = self.github.get_merged_pr_for_issue(issue_num)
                    if pr:
                        new_status = "✅ Complete (Merged)"
                    else:
                        new_status = "✅ Complete"
                else:
                    # Issue is open
                    if "In Progress" in current_status or "🔵" in current_status:
                        new_status = current_status  # Keep in progress
                    else:
                        new_status = "⚪ Not Started"

                # Update if different
                if new_status != current_status and "Complete" not in current_status:
                    updated_content = updated_content.replace(
                        match.group(0), match.group(1) + new_status
                    )
                    self.changes_made.append(
                        f"Updated Issue #{issue_num} status: {current_status} → {new_status}"
                    )

                    if self.verbose:
                        print(
                            f"  ✏️  Issue #{issue_num}: {current_status} → {new_status}",
                            file=sys.stderr,
                        )

        # Write back if changes were made
        if updated_content != content:
            self.tracking_file.write_text(updated_content)
            if self.verbose:
                print(f"  ✅ Updated {self.tracking_file.name}", file=sys.stderr)

    def _commit_and_sync(self):
        """Commit changes and sync with remote"""
        if self.verbose:
            print("\n💾 Committing and syncing changes...", file=sys.stderr)

        try:
            if not self.tracking_file.exists():
                if self.verbose:
                    print(
                        "  ℹ️  No tracking file present; no local tracker changes to commit.",
                        file=sys.stderr,
                    )
                return

            # Add tracking file
            subprocess.run(
                ["git", "add", str(self.tracking_file)],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            )

            # Create commit message
            commit_msg = "chore: Reconcile tracking file with GitHub state\n\n"
            for change in self.changes_made:
                commit_msg += f"- {change}\n"

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                if self.verbose:
                    print("  ✅ Committed changes", file=sys.stderr)

                # Push to remote
                push_result = subprocess.run(
                    ["git", "push"], cwd=REPO_ROOT, capture_output=True, text=True
                )

                if push_result.returncode == 0:
                    if self.verbose:
                        print("  ✅ Pushed to remote", file=sys.stderr)
                else:
                    print(f"  ⚠️  Push failed: {push_result.stderr}", file=sys.stderr)
            else:
                if "nothing to commit" in result.stdout:
                    if self.verbose:
                        print("  ℹ️  No changes to commit", file=sys.stderr)
                else:
                    print(f"  ❌ Commit failed: {result.stderr}", file=sys.stderr)

        except Exception as e:
            print(f"  ❌ Error during commit/sync: {e}", file=sys.stderr)


class GitHubClient:
    """Handles all GitHub API queries via gh CLI with proper timeout and error handling"""

    def __init__(self, repo: str, verbose: bool = False):
        self.repo = repo
        self.verbose = verbose
        self._cache = {}  # Simple cache to avoid repeated queries
        self._min_interval_seconds = max(
            0.0, float(os.getenv("NEXT_ISSUE_GH_MIN_INTERVAL", "1.0"))
        )
        self._last_request_monotonic: Optional[float] = None

    def _throttle_request(self) -> None:
        if self._min_interval_seconds <= 0:
            return

        now = time.monotonic()
        if self._last_request_monotonic is not None:
            elapsed = now - self._last_request_monotonic
            if elapsed < self._min_interval_seconds:
                time.sleep(self._min_interval_seconds - elapsed)
        self._last_request_monotonic = time.monotonic()

    def _run_gh_command(
        self, args: List[str], timeout: int = DEFAULT_TIMEOUT, cache_key: str = None
    ) -> Optional[Dict]:
        """
        Run a gh CLI command and return JSON output with timeout

        Args:
            args: Command arguments for gh CLI
            timeout: Timeout in seconds
            cache_key: Optional cache key to avoid repeated queries

        Returns:
            Parsed JSON response or None on error
        """
        # Check cache first
        if cache_key and cache_key in self._cache:
            if self.verbose:
                print(f"[DEBUG] Using cached result for: {cache_key}", file=sys.stderr)
            return self._cache[cache_key]

        try:
            cmd = ["gh"] + args + ["--repo", self.repo]
            if self.verbose:
                print(f"[DEBUG] Running: {' '.join(cmd[:5])}...", file=sys.stderr)

            self._throttle_request()

            result = run_gh_throttled(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                min_interval_seconds=0,
            )

            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                # Cache successful result
                if cache_key:
                    self._cache[cache_key] = data
                return data
            elif self.verbose and result.returncode != 0:
                print(
                    f"[DEBUG] Command failed (exit {result.returncode})",
                    file=sys.stderr,
                )

        except subprocess.TimeoutExpired:
            print(f"⚠️  GitHub API timeout after {timeout}s", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse GitHub response: {e}", file=sys.stderr)
        except FileNotFoundError:
            print(
                "❌ 'gh' CLI not found. Install: https://cli.github.com/",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as e:
            print(f"⚠️  Unexpected error: {e}", file=sys.stderr)

        return None

    def get_issues_by_numbers(
        self, issue_numbers: List[int], progress: Optional[ProgressIndicator] = None
    ) -> List[Dict]:
        """
        Get specific issues by number (efficient batch query)

        Args:
            issue_numbers: List of issue numbers to query
            progress: Optional progress indicator

        Returns:
            List of issue data dictionaries
        """
        issues = []

        if progress:
            progress.start(len(issue_numbers), "Querying GitHub issues")

        for issue_num in issue_numbers:
            cache_key = f"issue_{issue_num}"
            data = self._run_gh_command(
                [
                    "issue",
                    "view",
                    str(issue_num),
                    "--json",
                    "number,title,state,labels,closedAt",
                ],
                timeout=10,
                cache_key=cache_key,
            )

            if data:
                issues.append(data)

            if progress:
                progress.update()

        if progress:
            progress.finish(f"Queried {len(issues)}/{len(issue_numbers)} issues")

        return issues

    def get_open_issues(self, limit: int = 100) -> List[Dict]:
        """Get open issues in the repository, sorted by issue number."""
        data = self._run_gh_command(
            [
                "issue",
                "list",
                "--state",
                "open",
                "--limit",
                str(limit),
                "--json",
                "number,title,state,labels,closedAt",
            ],
            timeout=20,
        )

        if not data:
            return []

        return sorted(data, key=lambda issue: issue.get("number", 10**9))

    def is_issue_closed(self, issue_number: int) -> bool:
        """Check if an issue is closed on GitHub (with caching)"""
        cache_key = f"issue_state_{issue_number}"
        data = self._run_gh_command(
            ["issue", "view", str(issue_number), "--json", "state,closedAt"],
            timeout=10,
            cache_key=cache_key,
        )

        return data.get("state") == "CLOSED" if data else False

    def get_merged_pr_for_issue(self, issue_number: int) -> Optional[Dict]:
        """Get merged PR associated with an issue"""
        data = self._run_gh_command(
            [
                "pr",
                "list",
                "--state",
                "merged",
                "--search",
                f"#{issue_number}",
                "--limit",
                "3",
                "--json",
                "number,title,mergedAt,closedAt",
            ],
            timeout=15,
        )

        if data and len(data) > 0:
            # Find PR that references this issue number
            for pr in data:
                title = pr.get("title", "").lower()
                # Look for #number or [issue #number] or (issue #number)
                if (
                    f"#{issue_number}" in title
                    or f"issue #{issue_number}" in title
                    or f"[{issue_number}]" in title
                ):
                    return pr

        return None

    def is_issue_resolved(self, issue_number: int) -> bool:
        """
        Check if an issue is truly resolved (closed AND has merged PR)
        This is the source of truth for blocker resolution
        """
        # First check if issue is closed
        if not self.is_issue_closed(issue_number):
            return False

        # Then verify there's a merged PR
        pr = self.get_merged_pr_for_issue(issue_number)
        return pr is not None


class IssueKnowledge:
    """Manages learning from past issue resolutions"""

    def __init__(self, knowledge_file: Path):
        self.knowledge_file = knowledge_file
        self.data = self._load_knowledge()

    def _load_knowledge(self) -> Dict:
        """Load existing knowledge or create new"""
        if self.knowledge_file.exists():
            with open(self.knowledge_file, "r") as f:
                return json.load(f)
        return {
            "version": "1.0",
            "last_updated": None,
            "completed_issues": [],
            "patterns": {
                "avg_time_multiplier": 1.0,  # Actual vs estimated
                "common_blockers": [],
                "success_factors": [],
                "risk_factors": [],
            },
            "recommendations": {},
        }

    def save_knowledge(self):
        """Save knowledge to file"""
        self.data["last_updated"] = datetime.now().isoformat()
        with open(self.knowledge_file, "w") as f:
            json.dump(self.data, f, indent=2)

    def record_completion(
        self, issue_number: int, estimated_hours: float, actual_hours: float, notes: str
    ):
        """Record a completed issue"""
        completion = {
            "issue_number": issue_number,
            "estimated_hours": estimated_hours,
            "actual_hours": actual_hours,
            "multiplier": (
                actual_hours / estimated_hours if estimated_hours > 0 else 1.0
            ),
            "completed_at": datetime.now().isoformat(),
            "notes": notes,
        }
        self.data["completed_issues"].append(completion)

        # Update average multiplier
        multipliers = [c["multiplier"] for c in self.data["completed_issues"]]
        self.data["patterns"]["avg_time_multiplier"] = sum(multipliers) / len(
            multipliers
        )

        self.save_knowledge()

    def get_adjusted_estimate(self, estimated_hours: float) -> float:
        """Get time estimate adjusted by historical data"""
        multiplier = self.data["patterns"]["avg_time_multiplier"]
        return estimated_hours * multiplier

    def add_pattern(self, category: str, pattern: str):
        """Add a learned pattern"""
        if category in self.data["patterns"]:
            if pattern not in self.data["patterns"][category]:
                self.data["patterns"][category].append(pattern)
                self.save_knowledge()


class IssueSelector:
    """Selects the next issue to work on - Uses GitHub as source of truth"""

    def __init__(
        self, tracking_file: Path, knowledge: IssueKnowledge, github: GitHubClient
    ):
        self.tracking_file = tracking_file
        self.knowledge = knowledge
        self.github = github
        self.issues = self._parse_issues()

    def _parse_issues(self) -> List[Dict]:
        """
        Parse issues from GitHub (source of truth) with metadata from tracking file

        Uses SEQUENTIAL ORDER from tracking file (issues 24-58) not labels!

        GitHub provides:
        - Issue number, title, state (open/closed)

        Tracking file provides:
        - Estimated hours
        - Blockers
        - Phase information
        - Sequential order (24, 25, 26... 58)
        """
        # Primary source: live open issues from GitHub.
        # This prevents hard-stopping once legacy Step-1 windows are exhausted.
        github_issues = self.github.get_open_issues(limit=200)

        # Parse tracking file for metadata
        tracking_metadata = self._parse_tracking_file()

        # Merge GitHub state with tracking metadata
        issues = []
        for gh_issue in github_issues:
            issue_num = gh_issue["number"]
            metadata = tracking_metadata.get(issue_num, {})

            issues.append(
                {
                    "number": issue_num,
                    "title": gh_issue["title"],
                    "state": "Open",
                    "github_state": gh_issue["state"],  # Original GitHub state
                    "blockers": metadata.get("blockers", []),
                    "estimated_hours": metadata.get("estimated_hours", 4.0),
                    "adjusted_hours": self.knowledge.get_adjusted_estimate(
                        metadata.get("estimated_hours", 4.0)
                    ),
                    "phase": metadata.get("phase", "Unknown"),
                    "priority": metadata.get("priority", "Medium"),
                }
            )

        return issues

    def _parse_tracking_file(self) -> Dict[int, Dict]:
        """Parse tracking file to extract metadata (not state!) - optimized version"""
        if not self.tracking_file.exists():
            return {}

        metadata = {}
        content = self.tracking_file.read_text()

        # Parse each issue individually (much faster than complex regex)
        for issue_num in range(*STEP1_ISSUE_RANGE):
            # Find issue header
            issue_match = re.search(rf"### Issue #{issue_num}:", content)
            if not issue_match:
                continue

            # Extract section for this issue
            start = issue_match.start()
            next_issue_match = re.search(r"### Issue #", content[start + 10 :])
            end = (
                start + 10 + next_issue_match.start()
                if next_issue_match
                else len(content)
            )
            section = content[start:end]

            # Extract estimated hours (simple, fast)
            est_match = re.search(r"Estimated:.*?([\d.]+)", section, re.IGNORECASE)
            estimated_hours = float(est_match.group(1)) if est_match else 4.0

            # Extract blockers (simple, fast)
            blockers = []
            blocker_match = re.search(r"Blockers?:\s*([^\n]+)", section, re.IGNORECASE)
            if blocker_match:
                blocker_text = blocker_match.group(1)
                if not ("none" in blocker_text.lower()):
                    blockers = [
                        int(b.strip("#")) for b in re.findall(r"#(\d+)", blocker_text)
                    ]

            # Extract phase and priority from context
            phase = self._extract_phase(content, issue_num)
            priority = self._extract_priority(content, issue_num)

            metadata[issue_num] = {
                "blockers": blockers,
                "estimated_hours": estimated_hours,
                "phase": phase,
                "priority": priority,
            }

        return metadata

    def _extract_phase(self, content: str, issue_num: int) -> str:
        """Extract phase for an issue by finding the phase header before it"""
        # Find the issue position
        issue_pattern = rf"(?:###|\*\*) Issue #{issue_num}:"
        issue_match = re.search(issue_pattern, content)

        if not issue_match:
            return "Unknown"

        issue_pos = issue_match.start()

        # Find all phase headers before this issue (both with and without emoji)
        phase_pattern = r"##+ (?:📋 )?(Phase \d+: [^\n(]+)"
        phase_matches = list(re.finditer(phase_pattern, content[:issue_pos]))

        if phase_matches:
            # The last phase header before the issue is the one we want
            last_phase = phase_matches[-1].group(1).strip()
            return last_phase

        return "Unknown"

    def _extract_priority(self, content: str, issue_num: int) -> str:
        """Extract priority for an issue from tracking file or use defaults"""
        # Try to extract from tracking file first
        issue_pattern = rf"(?:###|\*\*) Issue #{issue_num}:.*?\n.*?Priority:.*?(CRITICAL|High|Medium|Low)"
        match = re.search(issue_pattern, content, re.DOTALL | re.IGNORECASE)

        if match:
            priority = match.group(1).strip()
            # Normalize to title case
            if priority.upper() == "CRITICAL":
                return "CRITICAL"
            return priority.capitalize()

        # Fallback to defaults based on issue number
        if issue_num in [24, 59]:
            return "CRITICAL"
        elif issue_num in [25, 26, 27, 28, 29]:
            return "High"
        else:
            return "Medium"

    def select_next_issue(self) -> Optional[Dict]:
        """
        Select the next issue to work on
        Uses GitHub as source of truth for issue state
        """
        # Filter to open issues only (GitHub state is source of truth)
        available = [i for i in self.issues if i["state"] == "Open"]

        if not available:
            return None

        # Filter by blockers resolved (check GitHub for each blocker)
        ready = []
        for issue in available:
            blockers_resolved = True

            if issue["blockers"]:
                for blocker_num in issue["blockers"]:
                    # Use GitHub as source of truth for blocker resolution
                    if not self.github.is_issue_resolved(blocker_num):
                        blockers_resolved = False
                        if self.github.verbose:
                            print(
                                f"[DEBUG] Issue #{issue['number']} blocked by #{blocker_num}",
                                file=sys.stderr,
                            )
                        break

            if blockers_resolved:
                ready.append(issue)

        if not ready:
            return None

        # Sort by: priority (CRITICAL first), then issue number (dependency order)
        priority_map = {"CRITICAL": 0, "High": 1, "Medium": 2, "Low": 3}
        ready.sort(key=lambda i: (priority_map.get(i["priority"], 99), i["number"]))

        return ready[0]

    def get_issue_context(self, issue_num: int) -> str:
        """Get full context for an issue from tracking file"""
        if not self.tracking_file.exists():
            return (
                "No local Step-1 tracking file is present in this repository. "
                "Use the live GitHub issue as the source of truth for planning and implementation context."
            )

        content = self.tracking_file.read_text()

        # Find the issue section (handles both ### and ** formats)
        pattern = rf"(?:###|\*\*) Issue #{issue_num}:.*?(?=\n(?:###|\*\*) Issue #|\n---\n\n###|\Z)"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            return match.group(0)
        return f"Issue #{issue_num} not found in tracking file"


def format_issue_recommendation(
    issue: Dict, context: str, knowledge: IssueKnowledge
) -> str:
    """Format the recommendation output"""
    output = []

    # The tracking file is useful metadata, but GitHub is the source of truth.
    # Guard against confusion when the local tracking title diverges from GitHub.
    tracking_title: Optional[str] = None
    first_line = context.strip().splitlines()[0] if context.strip() else ""
    title_match = re.search(r"Issue\s+#\d+:\s*(.+)$", first_line)
    if title_match:
        tracking_title = title_match.group(1).strip()

    output.append("=" * 80)
    output.append("NEXT ISSUE RECOMMENDATION")
    output.append("=" * 80)
    output.append("")
    output.append(f"🎯 Selected Issue: #{issue['number']}")
    output.append(f"📋 Title: {issue['title']}")
    output.append(f"📋 Phase: {issue['phase']}")
    output.append(f"⚡ Priority: {issue['priority']}")
    output.append(f"⏱️  Estimated Time: {issue['estimated_hours']:.1f} hours")
    output.append(
        f"📊 Adjusted Estimate: {issue['adjusted_hours']:.1f} hours "
        f"(based on {len(knowledge.data['completed_issues'])} completed issues)"
    )
    output.append(f"✅ GitHub State: {issue['github_state']} (verified via GitHub API)")
    output.append("")

    if issue["blockers"]:
        output.append(
            f"✅ Blockers Resolved: #{', #'.join(map(str, issue['blockers']))}"
        )
        output.append("   (Verified: All blockers are closed with merged PRs)")
        output.append("")
    else:
        output.append("✅ No Blockers")
        output.append("")

    if tracking_title and tracking_title != issue["title"]:
        output.append("⚠️  Tracking title mismatch detected")
        output.append(f"   • Local tracking: {tracking_title}")
        output.append(f"   • GitHub (source of truth): {issue['title']}")
        output.append("   • Use GitHub issue content for implementation decisions")
        output.append("")

    output.append("📝 Local Tracking Details (may be stale):")
    output.append("-" * 80)
    output.append(context)
    output.append("-" * 80)
    output.append("")

    # Learning insights
    if knowledge.data["completed_issues"]:
        output.append("💡 Insights from Previous Issues:")
        avg_mult = knowledge.data["patterns"]["avg_time_multiplier"]
        output.append(f"   • Average time multiplier: {avg_mult:.2f}x")
        output.append(
            f"   • Completed issues: {len(knowledge.data['completed_issues'])}"
        )

        if knowledge.data["patterns"]["success_factors"]:
            output.append("   • Success factors:")
            for factor in knowledge.data["patterns"]["success_factors"][-3:]:
                output.append(f"     - {factor}")
        output.append("")

    output.append("🚀 Next Steps:")
    output.append("   1. Read the full issue on GitHub:")
    output.append(f"      gh issue view {issue['number']} --repo {GITHUB_REPO}")
    output.append("")
    output.append("   2. Create feature branch:")
    output.append("      git checkout main && git pull origin main")
    output.append(f"      git checkout -b issue/{issue['number']}-<description>")
    output.append("")
    output.append("   3. Follow STEP-1-IMPLEMENTATION-WORKFLOW.md (10-step protocol)")
    output.append("      • Step 7 (Copilot review) is MANDATORY - never skip!")
    output.append("")
    output.append("=" * 80)

    return "\n".join(output)


def main():
    """Main entry point with timeout protection"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Select next issue to work on (with reconciliation)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information including GitHub API calls",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be selected without updating state or committing",
    )
    parser.add_argument(
        "--skip-reconcile",
        action="store_true",
        help="Skip reconciliation phase (not recommended)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Overall timeout in seconds (default: 180)",
    )
    args = parser.parse_args()

    # Set up signal handler for overall timeout
    def timeout_handler(signum, frame):
        print("\n❌ Operation timed out after {args.timeout}s")
        print("   Consider running with --skip-reconcile if reconciliation is slow")
        sys.exit(124)  # Standard timeout exit code

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(args.timeout)

    try:
        return _main_impl(args)
    except TimeoutError:
        print("\n❌ Operation timed out")
        return 124
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    finally:
        signal.alarm(0)  # Cancel alarm


def _main_impl(args):
    """Main implementation (separated for timeout handling)"""
    # Check if gh CLI is available
    try:
        run_gh_throttled(
            ["gh", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
            min_interval_seconds=0,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Error: 'gh' CLI not found or not authenticated.")
        print("\nInstall: https://cli.github.com/")
        print("Authenticate: gh auth login")
        return 1
    except subprocess.TimeoutExpired:
        print("⚠️  'gh' CLI check timed out, but continuing...")

    # Load knowledge
    knowledge = IssueKnowledge(KNOWLEDGE_FILE)

    # Create GitHub client
    github = GitHubClient(GITHUB_REPO, verbose=args.verbose)

    # PHASE 1: RECONCILIATION (unless skipped or dry-run)
    if not args.skip_reconcile and not args.dry_run:
        if not args.verbose:
            print("Phase 1: Reconciliation")

        reconciler = Reconciler(github, TRACKING_FILE, verbose=args.verbose)

        # Loop until everything is reconciled
        iteration = 0
        while iteration < MAX_RECONCILE_ITERATIONS:
            iteration += 1

            if args.verbose:
                print(
                    f"\n--- Reconciliation Iteration {iteration} ---", file=sys.stderr
                )

            changes_made = reconciler.reconcile()

            if not changes_made:
                break

            if iteration < MAX_RECONCILE_ITERATIONS:
                print(
                    f"   Changes made, running reconciliation again ({iteration}/{MAX_RECONCILE_ITERATIONS})...\n"
                )
        else:
            print(
                f"⚠️  Max reconciliation iterations ({MAX_RECONCILE_ITERATIONS}) reached"
            )
            print("   Some issues may still need manual attention\n")

    elif args.skip_reconcile:
        print("⚠️  Skipping reconciliation (--skip-reconcile flag)")

    print()  # Blank line for readability

    # PHASE 2: SELECTION
    if not args.verbose:
        print("Phase 2: Issue Selection")
    elif args.verbose:
        print("\n" + "=" * 80, file=sys.stderr)
        print("SELECTION PHASE", file=sys.stderr)
        print("=" * 80 + "\n", file=sys.stderr)

    # Create selector
    selector = IssueSelector(TRACKING_FILE, knowledge, github)

    if args.verbose:
        print(
            f"[DEBUG] Found {len(selector.issues)} candidate issues from live open query",
            file=sys.stderr,
        )
        open_count = len([i for i in selector.issues if i["state"] == "Open"])
        print(f"[DEBUG] {open_count} open issues", file=sys.stderr)

    # Select next issue
    next_issue = selector.select_next_issue()

    if not next_issue:
        print("❌ No issues available to work on.")
        print("\nPossible reasons:")
        print("   • All issues are complete")
        print("   • All remaining issues have unresolved blockers")
        print("\nRun with --verbose to see details:")
        print("   ./scripts/next-issue.py --verbose")
        return 1

    # Get full context from tracking file
    context = selector.get_issue_context(next_issue["number"])

    # Format and display recommendation
    recommendation = format_issue_recommendation(next_issue, context, knowledge)
    print(recommendation)

    # Save recommendation if not dry-run
    if not args.dry_run:
        knowledge.data["recommendations"]["last_selected"] = {
            "issue_number": next_issue["number"],
            "selected_at": datetime.now().isoformat(),
            "reason": f"Next in {next_issue['phase']}, all blockers resolved (verified via GitHub)",
            "github_state": next_issue["github_state"],
        }
        knowledge.save_knowledge()

    return 0


if __name__ == "__main__":
    sys.exit(main())
