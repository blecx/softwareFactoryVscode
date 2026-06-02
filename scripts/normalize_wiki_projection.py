#!/usr/bin/env python3
"""Normalize and consolidate wiki projection files.

This helper inspects the canonical live wiki clone (default: .tmp/wiki-launch/live-wiki)
and merges duplicate page files that differ only by slugification (spaces vs hyphens).

It prefers the page title listed in the projection manifest (manifests/wiki-projection-manifest.json)
when choosing the canonical filename. For duplicate groups it will preserve the projection
metadata block (the page header and projection note) from the canonical file and merge the
larger body from the duplicate into it. Duplicate files are removed.

Intended usage (dry-run):
  ./scripts/normalize_wiki_projection.py --dry-run

To apply changes and commit in the live wiki worktree:
  ./scripts/normalize_wiki_projection.py --apply

This script is defensive and intended as a maintenance helper for repository maintainers.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List


def load_manifest(manifest_path: Path) -> set:
    if not manifest_path.exists():
        return set()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = {f"{p.get('wiki_page')}.md" for p in data.get('pages', []) if p.get('wiki_page')}
    return names


def normalize_key(name: str) -> str:
    base = name[:-3] if name.endswith('.md') else name
    s = re.sub(r'[^0-9A-Za-z]+', '-', base).strip('-')
    return s.lower()


def extract_body(path: Path) -> List[str]:
    txt = path.read_text(encoding='utf-8')
    lines = txt.splitlines()
    if lines and lines[0].startswith('#'):
        lines = lines[1:]
    for i, line in enumerate(lines):
        if line.startswith('## '):
            return lines[i:]
    return lines


def merge_group(wiki_dir: Path, group: List[str], manifest_names: set) -> Dict:
    # choose canonical
    canonical = None
    for g in group:
        if g in manifest_names:
            canonical = g
            break
    if not canonical:
        for g in group:
            if ' ' in g:
                canonical = g
                break
    if not canonical:
        # fallback: longest file
        lengths = {g: len((wiki_dir / g).read_text(encoding='utf-8').splitlines()) for g in group}
        canonical = max(lengths, key=lambda k: lengths[k])

    canonical_path = wiki_dir / canonical
    projection_header = canonical_path.read_text(encoding='utf-8').splitlines()
    meta_end = None
    for i, line in enumerate(projection_header[1:], start=1):
        if line.startswith('## '):
            meta_end = i
            break
    if meta_end is None:
        meta_end = min(5, len(projection_header))

    projection_block = projection_header[:meta_end]

    bodies = []
    bodies.append(('canonical', extract_body(canonical_path), len(extract_body(canonical_path))))
    for o in group:
        if o == canonical:
            continue
        bodies.append((o, extract_body(wiki_dir / o), len(extract_body(wiki_dir / o))))

    primary = max(bodies, key=lambda t: t[2])[1] if bodies else []
    # assemble merged content
    content_lines = list(projection_block)
    content_lines.append('')
    if primary:
        while primary and primary[0].strip() == '':
            primary = primary[1:]
        content_lines.extend(primary)

    new_text = '\n'.join(content_lines).rstrip() + '\n'
    removed = []
    # write merged
    canonical_path.write_text(new_text, encoding='utf-8')
    # remove others
    for o in group:
        if o == canonical:
            continue
        p = wiki_dir / o
        if p.exists():
            p.unlink()
            removed.append(o)

    return {'canonical': canonical, 'removed': removed}


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

    manifest_names = load_manifest(args.manifest)

    files = [p.name for p in wiki_dir.glob('*.md')]
    groups: Dict[str, List[str]] = {}
    for f in files:
        key = normalize_key(f)
        groups.setdefault(key, []).append(f)

    ops = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        ops.append((key, group))

    if not ops:
        print('No duplicate slug groups found')
        return 0

    print('Found duplicate groups:')
    for key, group in ops:
        print(' -', key, '->', group)

    if args.dry_run and not args.apply:
        print('\nDry run complete; no changes applied')
        return 0

    results = []
    for key, group in ops:
        res = merge_group(wiki_dir, group, manifest_names)
        results.append(res)

    # commit
    subprocess.run(['git', '-C', str(wiki_dir), 'add', '.'], check=False)
    commit_msg = 'wiki-update: merge slugified duplicate pages into canonical titles'
    subprocess.run(['git', '-C', str(wiki_dir), 'commit', '-m', commit_msg], check=False)

    print('Applied merge operations:')
    for r in results:
        print(' *', r['canonical'], ' <- removed:', r['removed'])

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
