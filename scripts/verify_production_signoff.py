#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List

DEFAULT_SIGN_OFF_FILE = ".tmp/production-readiness/latest.json"

SECRET_PATTERNS = [
    re.compile(r"gh[posura]_[a-zA-Z0-9_]{36,}"),
    re.compile(r"sk-[a-zA-Z0-9_]{40,}"),
    re.compile(r"ey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT
]

SECRET_KEY_WORDS = ["secret", "token", "password", "api_key", "apikey"]


def contains_secret(val: Any) -> bool:
    if isinstance(val, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(val):
                return True
    return False


def check_dict_for_secrets(data: Dict[str, Any], path: str = "") -> List[str]:
    violations = []
    if not isinstance(data, dict):
        return violations

    for k, v in data.items():
        current_path = f"{path}.{k}" if path else k

        # Check if key implies a secret
        if any(word in k.lower() for word in SECRET_KEY_WORDS):
            # If it's a non-empty string that isn't a safe placeholder
            if (
                isinstance(v, str)
                and len(v) > 0
                and v.lower() not in ["hidden", "redacted", "xxx"]
            ):
                violations.append(
                    f"Key '{current_path}' looks like a secret but has unredacted value."
                )

        if contains_secret(v):
            violations.append(f"Value at '{current_path}' looks like a secret.")

        if isinstance(v, dict):
            violations.extend(check_dict_for_secrets(v, current_path))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                list_path = f"{current_path}[{i}]"
                if isinstance(item, dict):
                    violations.extend(check_dict_for_secrets(item, list_path))
                elif contains_secret(item):
                    violations.append(f"Value at '{list_path}' looks like a secret.")
    return violations


from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class JobEvidence:
    name: str
    conclusion: str


@dataclass
class ArtifactEvidence:
    name: str
    url: str


@dataclass
class GitHubCIEvidence:
    run_id: str
    run_url: str
    head_sha: str
    branch: str
    workflow_name: str
    jobs: List[JobEvidence]
    artifacts: List[ArtifactEvidence] = field(default_factory=list)


def parse_ci_evidence(
    payload: Dict[str, Any]
) -> Tuple[Optional[GitHubCIEvidence], List[str]]:
    if not payload:
        return None, ["No CI evidence provided."]

    blockers = []
    secret_violations = check_dict_for_secrets(payload)
    if secret_violations:
        blockers.extend(secret_violations)

    required_fields = [
        "run_id",
        "run_url",
        "head_sha",
        "branch",
        "workflow_name",
        "jobs",
    ]
    for f in required_fields:
        if f not in payload:
            blockers.append(f"Missing required field: '{f}'")
        elif payload[f] is None or payload[f] == "":
            blockers.append(f"Field '{f}' cannot be empty.")

    if blockers:
        return None, blockers

    jobs = []
    jobs_payload = payload.get("jobs", [])
    if not isinstance(jobs_payload, list) or len(jobs_payload) == 0:
        blockers.append("Jobs must be a non-empty list.")
    else:
        for i, j in enumerate(jobs_payload):
            if not isinstance(j, dict):
                blockers.append(f"Job at index {i} is malformed.")
                continue
            name = j.get("name")
            conclusion = j.get("conclusion")
            if not name or not conclusion:
                blockers.append(f"Job at index {i} is missing name or conclusion.")
            else:
                jobs.append(JobEvidence(name=str(name), conclusion=str(conclusion)))

    artifacts = []
    artifacts_payload = payload.get("artifacts", [])
    if isinstance(artifacts_payload, list):
        for i, a in enumerate(artifacts_payload):
            if not isinstance(a, dict):
                blockers.append(f"Artifact at index {i} is malformed.")
                continue
            name = a.get("name")
            url = a.get("url")
            if not name or not url:
                blockers.append(f"Artifact at index {i} is missing name or url.")
            else:
                artifacts.append(ArtifactEvidence(name=str(name), url=str(url)))
    elif artifacts_payload:
        blockers.append("Artifacts must be a list if provided.")

    if blockers:
        return None, blockers

    try:
        model = GitHubCIEvidence(
            run_id=str(payload["run_id"]),
            run_url=str(payload["run_url"]),
            head_sha=str(payload["head_sha"]),
            branch=str(payload["branch"]),
            workflow_name=str(payload["workflow_name"]),
            jobs=jobs,
            artifacts=artifacts,
        )
        return model, []
    except Exception as e:
        return None, [f"Failed to parse CI evidence model: {str(e)}"]


def verify_ci_evidence(
    ci_evidence: Dict[str, Any], required_jobs: List[str] = None
) -> Dict[str, Any]:
    model, blockers = parse_ci_evidence(ci_evidence)
    if not model:
        return {"valid": False, "blockers": blockers}

    if required_jobs is None:
        required_jobs = []

    # Run gh run view
    try:
        gh_cmd = [
            "gh",
            "run",
            "view",
            model.run_id,
            "--json",
            "conclusion,headSha,jobs,status",
        ]
        result = subprocess.run(gh_cmd, capture_output=True, text=True, check=True)
        gh_data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        blockers.append(
            f"GitHub CLI query failed: {e.stderr.strip() if e.stderr else e.strerror}"
        )
        return {"valid": False, "blockers": blockers}
    except json.JSONDecodeError:
        blockers.append("Failed to parse GitHub CLI JSON output")
        return {"valid": False, "blockers": blockers}

    if gh_data.get("headSha") != model.head_sha:
        blockers.append(
            f"SHA mismatch: GitHub run {model.run_id} head_sha {gh_data.get('headSha')} != provided {model.head_sha}"
        )

    if gh_data.get("conclusion") != "success":
        blockers.append(
            f"GitHub run {model.run_id} conclusion is not success (it is {gh_data.get('conclusion')})"
        )

    if gh_data.get("status") not in ("completed", "success"):
        # "success" is conclusion, but just making sure it's completed
        if gh_data.get("status") != "completed":
            blockers.append(
                f"GitHub run {model.run_id} is not completed (status: {gh_data.get('status')})"
            )

    gh_jobs = gh_data.get("jobs", [])
    gh_jobs_map = {j["name"]: j for j in gh_jobs}

    for rj in required_jobs:
        if rj not in gh_jobs_map:
            blockers.append(
                f"Required job '{rj}' was not found in GitHub run {model.run_id}"
            )
        else:
            job_data = gh_jobs_map[rj]
            if job_data.get("conclusion") != "success":
                blockers.append(
                    f"Required job '{rj}' did not succeed (conclusion: {job_data.get('conclusion')})"
                )

    for job in model.jobs:
        if job.conclusion != "success":
            blockers.append(
                f"CI signoff conclusion is not success: {job.conclusion} for provided job {job.name}"
            )

    return {"valid": len(blockers) == 0, "blockers": blockers}


def verify_signoff(filepath: str, required_jobs: List[str] = None) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        return {
            "valid": False,
            "blockers": [
                (
                    f"No production signoff evidence found at {filepath}. "
                    "Please generate production-readiness evidence first."
                )
            ],
        }

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"valid": False, "blockers": [f"File {filepath} is not valid JSON."]}

    blockers = []
    required_fields = ["command", "status", "timestamp", "evidence"]
    for field_name in required_fields:
        if field_name not in data:
            blockers.append(f"Missing required field: '{field_name}'")

    if "status" in data and data["status"] != "success":
        blockers.append(f"Signoff status is not success: {data['status']}")

    if "evidence" in data and "github_ci" in data["evidence"]:
        ci_result = verify_ci_evidence(data["evidence"]["github_ci"], required_jobs)
        if not ci_result["valid"]:
            blockers.extend(ci_result.get("blockers", []))

    secret_violations = check_dict_for_secrets(data)
    blockers.extend(secret_violations)

    return {"valid": len(blockers) == 0, "blockers": blockers}


def main():
    parser = argparse.ArgumentParser(description="Verify Production Signoff")
    parser.add_argument(
        "filepath",
        nargs="?",
        default=DEFAULT_SIGN_OFF_FILE,
        help="Path to signoff JSON file",
    )
    parser.add_argument(
        "--required-job",
        action="append",
        default=[],
        help="Required CI job name. Can be specified multiple times.",
    )
    args = parser.parse_args()

    filepath = args.filepath
    required_jobs = args.required_job

    result = verify_signoff(filepath, required_jobs)
    if not result["valid"]:
        print("Production signoff verification failed:")
        for blocker in result["blockers"]:
            print(f" - {blocker}")
        sys.exit(1)

    print("Production signoff evidence is valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
