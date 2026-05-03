#!/usr/bin/env python3
"""CI simulation engine.

Runs ``local_ci_parity.py`` bundles inside a Docker container that mirrors the
GitHub Actions ``ubuntu-latest`` + Python 3.13 environment.  Compares the
results with a local baseline run to surface local↔remote drift **before
pushing**.

Usage (invoked from ``todo_app_regression.py``)::

    from ci_simulation import run_ci_simulation
    result = run_ci_simulation(repo_root, throwaway_root)

The returned dict is embedded in the regression report under the
``ci_simulation`` key.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Dockerfile path relative to the repository root
DOCKERFILE_REL = Path("docker") / "ci-simulation" / "Dockerfile"

IMAGE_NAME_PREFIX = "factory-ci-simulation"

# Bundles safe to simulate (no external services, no Docker-in-Docker needed)
SIMULATABLE_BUNDLES: tuple[str, ...] = ("docs-contract", "workflow-contract")

# Drift category labels
DRIFT_LOCAL_PASS_CI_FAIL = "LOCAL_PASS_CI_FAIL"  # primary drift: will fail on GitHub
DRIFT_LOCAL_FAIL_CI_PASS = "LOCAL_FAIL_CI_PASS"  # inverse: local is stricter
CONSISTENT_PASS = "CONSISTENT_PASS"  # both pass – clean
CONSISTENT_FAIL = "CONSISTENT_FAIL"  # both fail – fix before pushing


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BundleSimResult:
    """Outcome of running a single parity bundle in one environment."""

    bundle: str
    exit_code: int | None
    passed: bool
    stdout: str
    stderr: str
    elapsed_seconds: float
    error: str = ""


@dataclass
class DriftFinding:
    """Comparison between local and CI results for one bundle."""

    bundle: str
    category: str
    local_passed: bool
    ci_passed: bool
    detail: str


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------


def detect_docker_available() -> bool:
    """Return ``True`` if Docker CLI is present and the daemon responds."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _image_tag(dockerfile_path: Path) -> str:
    """Derive a stable, reproducible image tag from the Dockerfile content hash.

    The tag changes only when the Dockerfile itself changes, so repeated runs
    reuse the cached image without an unnecessary rebuild.
    """
    content = dockerfile_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()[:12]
    return f"{IMAGE_NAME_PREFIX}:{digest}"


def build_ci_simulation_image(dockerfile_path: Path) -> tuple[str, str, bool]:
    """Build the CI simulation image.

    Returns ``(tag, build_log, success)``.  Skips the build when an image with
    the same content-hash tag already exists in the local Docker cache.
    """
    tag = _image_tag(dockerfile_path)

    # Fast-path: image is already cached locally
    check = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        timeout=10,
    )
    if check.returncode == 0:
        return tag, f"Image {tag} already present; build skipped.", True

    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            tag,
            "-f",
            str(dockerfile_path),
            str(dockerfile_path.parent),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    log = result.stdout + result.stderr
    return tag, log, result.returncode == 0


# ---------------------------------------------------------------------------
# Bundle runners
# ---------------------------------------------------------------------------


def run_bundle_local(
    repo_root: Path,
    bundle: str,
    level: str,
    base_rev: str,
    python_bin: str,
) -> BundleSimResult:
    """Execute a single parity bundle using the host Python environment."""
    start = time.monotonic()
    cmd = [
        python_bin,
        str(repo_root / "scripts" / "local_ci_parity.py"),
        "--level",
        level,
        "--base-rev",
        base_rev,
        "--ci-run-bundle",
        bundle,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=repo_root,
        )
        elapsed = time.monotonic() - start
        return BundleSimResult(
            bundle=bundle,
            exit_code=result.returncode,
            passed=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=round(elapsed, 2),
        )
    except subprocess.TimeoutExpired:
        return BundleSimResult(
            bundle=bundle,
            exit_code=None,
            passed=False,
            stdout="",
            stderr="",
            elapsed_seconds=round(time.monotonic() - start, 2),
            error="timeout",
        )


def run_bundle_in_container(
    image_tag: str,
    checkout_path: Path,
    bundle: str,
    level: str,
    base_rev: str,
) -> BundleSimResult:
    """Execute a single parity bundle inside the CI simulation container.

    The container receives a clean git worktree bind-mounted at ``/repo``.
    It runs ``setup.sh`` (mirroring GitHub's "Install dependencies" step) and
    then calls ``local_ci_parity.py`` with the given bundle.
    """
    start = time.monotonic()
    setup_and_run = (
        "bash ./setup.sh && "
        f"./.venv/bin/python ./scripts/local_ci_parity.py "
        f"--level {level} "
        f"--base-rev {base_rev} "
        f"--ci-run-bundle {bundle}"
    )
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{checkout_path}:/repo",
        "--workdir",
        "/repo",
        image_tag,
        "bash",
        "-c",
        setup_and_run,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        elapsed = time.monotonic() - start
        return BundleSimResult(
            bundle=bundle,
            exit_code=result.returncode,
            passed=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=round(elapsed, 2),
        )
    except subprocess.TimeoutExpired:
        return BundleSimResult(
            bundle=bundle,
            exit_code=None,
            passed=False,
            stdout="",
            stderr="",
            elapsed_seconds=round(time.monotonic() - start, 2),
            error="timeout",
        )


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def compute_drift(
    local_results: list[BundleSimResult],
    ci_results: list[BundleSimResult],
) -> list[DriftFinding]:
    """Compare local and CI bundle results and categorise each bundle.

    Returns a list of :class:`DriftFinding` objects sorted by bundle name.
    """
    local_by = {r.bundle: r for r in local_results}
    ci_by = {r.bundle: r for r in ci_results}
    findings: list[DriftFinding] = []

    for bundle in sorted(set(local_by) | set(ci_by)):
        local = local_by.get(bundle)
        ci = ci_by.get(bundle)

        if local is None or ci is None:
            continue

        local_passed = local.passed
        ci_passed = ci.passed

        if local_passed and not ci_passed:
            category = DRIFT_LOCAL_PASS_CI_FAIL
            detail = (
                f"Bundle '{bundle}' passes locally but FAILS in the CI simulation. "
                f"CI exit_code={ci.exit_code}. "
                "This is the primary drift vector: commits that pass local parity "
                "will fail on GitHub CI."
            )
        elif not local_passed and ci_passed:
            category = DRIFT_LOCAL_FAIL_CI_PASS
            detail = (
                f"Bundle '{bundle}' fails locally but PASSES in the CI simulation. "
                f"Local exit_code={local.exit_code}. "
                "Local environment may be stricter or have extra state absent from CI."
            )
        elif local_passed and ci_passed:
            category = CONSISTENT_PASS
            detail = f"Bundle '{bundle}' passes in both local and CI simulation."
        else:
            category = CONSISTENT_FAIL
            detail = (
                f"Bundle '{bundle}' fails in both local and CI simulation. "
                f"Local exit_code={local.exit_code}, CI exit_code={ci.exit_code}. "
                "Fix the failure before pushing — it will also fail on GitHub CI."
            )

        findings.append(
            DriftFinding(
                bundle=bundle,
                category=category,
                local_passed=local_passed,
                ci_passed=ci_passed,
                detail=detail,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Checkout helpers
# ---------------------------------------------------------------------------


def create_simulation_checkout(repo_root: Path, worktree_parent: Path) -> Path | None:
    """Create a clean git worktree for the Docker container to write into.

    The container runs ``setup.sh`` which creates a ``.venv`` directory.
    Using a fresh worktree keeps the host ``.venv`` completely untouched.
    Returns the worktree path on success, ``None`` on failure.
    """
    worktree_parent.mkdir(parents=True, exist_ok=True)
    checkout_path = worktree_parent / "sim-checkout"

    # Remove any leftover worktree from a previous (possibly interrupted) run
    if checkout_path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(checkout_path)],
            capture_output=True,
            cwd=repo_root,
            timeout=30,
        )
        if checkout_path.exists():
            shutil.rmtree(checkout_path, ignore_errors=True)

    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(checkout_path), "HEAD"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=60,
    )
    if result.returncode != 0:
        return None
    return checkout_path


def cleanup_simulation_checkout(repo_root: Path, checkout_path: Path) -> None:
    """Remove the simulation git worktree and any leftover files."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(checkout_path)],
        capture_output=True,
        cwd=repo_root,
        timeout=30,
    )
    if checkout_path.exists():
        shutil.rmtree(checkout_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _bundle_result_to_dict(r: BundleSimResult) -> dict[str, Any]:
    return {
        "bundle": r.bundle,
        "passed": r.passed,
        "exit_code": r.exit_code,
        "elapsed_seconds": r.elapsed_seconds,
        # Truncate verbose outputs so the report stays readable
        "stdout_tail": r.stdout[-2000:] if r.stdout else "",
        "stderr_tail": r.stderr[-1000:] if r.stderr else "",
        "error": r.error,
    }


def _finding_to_dict(f: DriftFinding) -> dict[str, Any]:
    return {
        "bundle": f.bundle,
        "category": f.category,
        "local_passed": f.local_passed,
        "ci_passed": f.ci_passed,
        "detail": f.detail,
    }


def _skipped_report(
    *,
    skip_reason: str,
    bundles: tuple[str, ...],
    elapsed: float,
) -> dict[str, Any]:
    return {
        "available": False,
        "skipped": True,
        "skip_reason": skip_reason,
        "image_tag": "",
        "dockerfile_path": str(DOCKERFILE_REL),
        "bundles_simulated": [],
        "bundles_skipped": list(bundles),
        "local_results": [],
        "ci_results": [],
        "drift_findings": [],
        "drift_detected": False,
        "os_note": "",
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


def run_ci_simulation(
    repo_root: Path,
    throwaway_root: Path,
    *,
    bundles: tuple[str, ...] = SIMULATABLE_BUNDLES,
    level: str = "focused-local",
    base_rev: str = "HEAD^",
    python_bin: str = "./.venv/bin/python",
) -> dict[str, Any]:
    """Run CI simulation for *bundles* and return a structured report dict.

    Each bundle is executed **twice**: once in the host Python environment and
    once inside a Docker container that mirrors GitHub's ``ubuntu-latest`` +
    Python 3.13 setup.  The two results are compared and any divergence is
    surfaced as drift findings under the ``drift_findings`` key.

    The returned dict is suitable for embedding in the regression report under
    the ``ci_simulation`` key.

    When Docker is unavailable, or when any prerequisite fails, the function
    returns a graceful SKIPPED report (``skipped=True``) instead of raising.
    """
    start = time.monotonic()

    if not detect_docker_available():
        return _skipped_report(
            skip_reason="Docker daemon is not available on this host.",
            bundles=bundles,
            elapsed=0.0,
        )

    dockerfile_path = repo_root / DOCKERFILE_REL
    if not dockerfile_path.exists():
        return _skipped_report(
            skip_reason=f"CI simulation Dockerfile not found at {DOCKERFILE_REL}.",
            bundles=bundles,
            elapsed=0.0,
        )

    image_tag, build_log, build_ok = build_ci_simulation_image(dockerfile_path)
    if not build_ok:
        return _skipped_report(
            skip_reason=f"CI simulation image build failed: {build_log[:500]}",
            bundles=bundles,
            elapsed=round(time.monotonic() - start, 2),
        )

    sim_worktree_parent = throwaway_root / "workspace" / "artifacts" / "ci-simulation"
    checkout_path = create_simulation_checkout(repo_root, sim_worktree_parent)
    if checkout_path is None:
        return _skipped_report(
            skip_reason="Failed to create a fresh git worktree for the CI simulation.",
            bundles=bundles,
            elapsed=round(time.monotonic() - start, 2),
        )

    try:
        local_results: list[BundleSimResult] = []
        ci_results: list[BundleSimResult] = []

        for bundle in bundles:
            print(f"  [ci-sim] local:  bundle={bundle}")
            local_results.append(
                run_bundle_local(repo_root, bundle, level, base_rev, python_bin)
            )
            print(f"  [ci-sim] docker: bundle={bundle}")
            ci_results.append(
                run_bundle_in_container(
                    image_tag, checkout_path, bundle, level, "HEAD^"
                )
            )

        drift_findings = compute_drift(local_results, ci_results)
        drift_detected = any(
            f.category in (DRIFT_LOCAL_PASS_CI_FAIL, DRIFT_LOCAL_FAIL_CI_PASS)
            for f in drift_findings
        )

        return {
            "available": True,
            "skipped": False,
            "skip_reason": "",
            "image_tag": image_tag,
            "dockerfile_path": str(DOCKERFILE_REL),
            "bundles_simulated": list(bundles),
            "bundles_skipped": [],
            "local_results": [_bundle_result_to_dict(r) for r in local_results],
            "ci_results": [_bundle_result_to_dict(r) for r in ci_results],
            "drift_findings": [_finding_to_dict(f) for f in drift_findings],
            "drift_detected": drift_detected,
            "os_note": (
                "CI simulation uses python:3.13-slim (Debian bookworm). "
                "GitHub CI uses ubuntu-latest (Ubuntu 24.04). "
                "OS-level package differences may cause additional drift "
                "not visible in this simulation."
            ),
            "elapsed_seconds": round(time.monotonic() - start, 2),
        }
    finally:
        cleanup_simulation_checkout(repo_root, checkout_path)
