import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml


def parse_frontmatter(content):
    meta = {}

    # Check top-level frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                meta.update(yaml.safe_load(parts[1]) or {})
            except Exception:
                pass

    # Check chatagent frontmatter
    chatagent_match = re.search(r"```chatagent\n(.*?)\n```", content, re.DOTALL)
    if chatagent_match:
        inner = chatagent_match.group(1)
        if inner.startswith("---"):
            parts = inner.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta.update(yaml.safe_load(parts[1]) or {})
                except Exception:
                    pass

    return meta, content


def count_heading(content, heading):
    # Matches exactly heading, e.g., "## Objective" at start of line
    pattern = re.compile(rf"^{heading}\s*$", re.MULTILINE | re.IGNORECASE)
    return len(pattern.findall(content))


def extract_authority_references(content):
    # simple match for things like .copilot/skills/..., or docs/architecture/...
    refs = re.findall(
        r"((?:\.copilot|\.github|docs/architecture)/[a-zA-Z0-9_\-\./\\]+\.md)", content
    )
    return list(set(refs))


def validate_file(filepath, repo_root):
    content = filepath.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)

    errors = []

    # 1. Check placeholder
    if "Follow domain guidelines." in content:
        errors.append("Contains placeholder 'Follow domain guidelines.'")

    # Determine form
    canonical_form = "Unknown"
    is_chatagent = "```chatagent" in content
    has_user_req = "User request:" in content

    if is_chatagent:
        canonical_form = "Form C"
    elif has_user_req:
        canonical_form = "Form D"
    elif content.startswith("---"):
        canonical_form = "Form B"
    else:
        canonical_form = "Form A"

    # Check headings for Form B and C
    if canonical_form in ("Form B", "Form C"):
        for heading in ["## Objective"]:
            count = count_heading(content, heading)
            if count != 1:
                errors.append(f"Expected exactly one '{heading}', found {count}")

    # Check authority references
    auth_refs = extract_authority_references(content)
    if canonical_form in ("Form C", "Form D") and not auth_refs:
        if not re.search(r"Required Sources", content, re.IGNORECASE):
            errors.append(
                "Missing authority references (no links to canonical owner paths)"
            )

    # Check duplicate headings as per drift policy
    headings = re.findall(r"^##\s+(.*)$", content, re.MULTILINE)
    seen = set()
    for h in headings:
        h_lower = h.lower().strip()
        if h_lower in seen:
            errors.append(f"Duplicate heading found: '## {h.strip()}'")
        seen.add(h_lower)

    # Extract domain and authority owner loosely
    domain = meta.get("domain", filepath.parent.name)
    owner = meta.get("owner", "Unknown")

    rel_path = str(filepath.relative_to(repo_root))

    return {
        "file": rel_path,
        "form": canonical_form,
        "name": meta.get("name", filepath.stem),
        "description": meta.get("description", ""),
        "domain": domain,
        "authority_owner": owner,
        "authority_references": auth_refs,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".", help="Root of repo")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    target_dirs = [
        repo_root / ".copilot" / "skills",
        repo_root / ".github" / "prompts",
        repo_root / ".github" / "agents",
    ]

    results = []
    has_errors = False

    for d in target_dirs:
        if not d.exists():
            continue
        for md_file in d.rglob("*.md"):
            # Ignore assets, references
            if (
                md_file.parent.name in ("assets", "references")
                or "_Sidebar" in md_file.name
                or "_Footer" in md_file.name
                or md_file.name == "Home.md"
                or md_file.name.endswith("README.md")
            ):
                continue

            res = validate_file(md_file, repo_root)
            results.append(res)

            if res["errors"]:
                print(f"FAIL: {res['file']}")
                for e in res["errors"]:
                    print(f"  - {e}")
                has_errors = True
            else:
                print(f"PASS: {res['file']}")

    catalog_path = repo_root / "manifests" / "ai-surface-catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    catalog_entries = [{k: v for k, v in r.items() if k != "errors"} for r in results]

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog_entries, f, indent=2)

    print(
        f"\nWrote generated catalog to {catalog_path.relative_to(repo_root)} with {len(catalog_entries)} surfaces."
    )
    if has_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
