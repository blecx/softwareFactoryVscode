#!/usr/bin/env python3
"""wiki_update helper

Small wrapper to ensure manifest-derived filenames are enforced in the live wiki
clone and to run the normalization/merge helper as part of the update flow.

Usage:
  ./scripts/wiki_update.py [--wiki-dir .tmp/wiki-launch/live-wiki] [--manifest manifests/wiki-projection-manifest.json] [--dry-run] [--apply]

This script intentionally keeps its behavior minimal: it will rename existing files
whose normalized slug key matches a manifest entry to the canonical manifest filename
and then invoke the normalization helper to merge/clean duplicates and commit the
result in the live wiki worktree.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List


def normalize_key(name: str) -> str:
    base = name[:-3] if name.endswith('.md') else name
    s = re.sub(r'[^0-9A-Za-z]+', '-', base).strip('-')
    return s.lower()


def load_manifest(manifest_path: Path) -> Dict[str, str]:
    if not manifest_path.exists():
        return {}
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    result = {}
    for p in data.get('pages', []):
        name = p.get('wiki_page')
        if name:
            result[normalize_key(f"{name}.md")] = f"{name}.md"
    return result


def plan_renames(wiki_dir: Path, manifest_map: Dict[str, str]) -> List[Dict[str, str]]:
    planned = []
    files = [p.name for p in wiki_dir.glob('*.md')]
    by_key: Dict[str, List[str]] = {}
    for f in files:
        k = normalize_key(f)
        by_key.setdefault(k, []).append(f)

    for key, group in by_key.items():
        canonical = manifest_map.get(key)
        if not canonical:
            # manifest doesn't list this normalized key; skip
            continue
        if canonical in group:
            # canonical file already present; skip renaming others
            continue
        # pick a candidate to rename (prefer hyphenated or longest)
        candidate = None
        # prefer exact slugified (hyphenated) match
        for g in group:
            if '-' in g:
                candidate = g
                break
        if not candidate:
            # fallback to longest file name
            candidate = max(group, key=lambda x: len(x))

        planned.append({'from': candidate, 'to': canonical})
    return planned


def apply_renames(wiki_dir: Path, planned: List[Dict[str, str]]) -> None:
    for op in planned:
        src = wiki_dir / op['from']
        dst = wiki_dir / op['to']
        if dst.exists():
            # if dst exists, skip; normalization will merge later
            print(f"skip rename, target exists: {dst.name}")
            continue
        print(f"rename: {src.name} -> {dst.name}")
        src.rename(dst)


def run_normalizer(wiki_dir: Path, apply_mode: bool) -> None:
    # call normalize_wiki_projection.py in repo scripts
    cmd = [str(Path('scripts/normalize_wiki_projection.py').resolve())]
    if not apply_mode:
        cmd.append('--dry-run')
    else:
        cmd.append('--apply')
    # Run using the repo python interpreter if available
    print('Running normalizer:', ' '.join(cmd))
    subprocess.run(['./.venv/bin/python'] + cmd, check=False)


def commit_if_needed(wiki_dir: Path, message: str) -> None:
    # add & commit any changes in the live wiki worktree
    subprocess.run(['git', '-C', str(wiki_dir), 'add', '.'], check=False)
    # only commit if something to commit
    res = subprocess.run(['git', '-C', str(wiki_dir), 'status', '--porcelain'], capture_output=True, text=True)
    if res.stdout.strip():
        subprocess.run(['git', '-C', str(wiki_dir), 'commit', '-m', message], check=False)
        print('Committed wiki worktree changes')
    else:
        print('No changes to commit in wiki worktree')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--wiki-dir', type=Path, default=Path('.tmp/wiki-launch/live-wiki'))
    parser.add_argument('--manifest', type=Path, default=Path('manifests/wiki-projection-manifest.json'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.exists():
        print('wiki dir does not exist:', wiki_dir)
        return 2

    manifest_map = load_manifest(args.manifest)
    if not manifest_map:
        print('manifest empty or missing:', args.manifest)
        return 2

    planned = plan_renames(wiki_dir, manifest_map)
    if not planned:
        print('No manifest-driven renames planned')
    else:
        print('Planned renames:')
        for op in planned:
            print(' -', op['from'], '->', op['to'])

    if args.dry_run and not args.apply:
        print('dry-run only; no changes applied')
        return 0

    if planned and args.apply:
        apply_renames(wiki_dir, planned)
        # commit renames before running normalizer so normalizer sees canonical filenames
        commit_if_needed(wiki_dir, 'wiki-update: enforce manifest-derived filenames')

    # run the normalizer (dry-run when not apply)
    run_normalizer(wiki_dir, apply_mode=args.apply)

    # normalize will commit; ensure any remaining renames get committed
    if args.apply:
        commit_if_needed(wiki_dir, 'wiki-update: post-normalizer cleanup')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
