#!/usr/bin/env python3
import json
import os
import re
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


def verify_ci_evidence(ci_evidence: Dict[str, Any]) -> Dict[str, Any]:
    model, blockers = parse_ci_evidence(ci_evidence)
    if not model:
        return {"valid": False, "blockers": blockers}

    for job in model.jobs:
        if job.conclusion != "success":
            blockers.append(
                f"CI signoff conclusion is not success: {job.conclusion} for job {job.name}"
            )

    return {"valid": len(blockers) == 0, "blockers": blockers}


def verify_signoff(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        return {
            "valid": False,
            "blockers": [
                f"No production signoff evidence found at {filepath}. Please generate production-readiness evidence first."
            ],
        }

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"valid": False, "blockers": [f"File {filepath} is not valid JSON."]}

    blockers = []
    required_fields = ["command", "status", "timestamp", "evidence"]
    for field in required_fields:
        if field not in data:
            blockers.append(f"Missing required field: '{field}'")

    if "status" in data and data["status"] != "success":
        blockers.append(f"Signoff status is not success: {data['status']}")

    secret_violations = check_dict_for_secrets(data)
    blockers.extend(secret_violations)

    return {"valid": len(blockers) == 0, "blockers": blockers}


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIGN_OFF_FILE
    result = verify_signoff(filepath)
    if not result["valid"]:
        print("Production signoff verification failed:")
        for blocker in result["blockers"]:
            print(f" - {blocker}")
        sys.exit(1)

    print("Production signoff evidence is valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
