#!/usr/bin/env python3
"""Check .en.md files for code block mismatches compared to Chinese originals.

Usage:
    python scripts/check_codeblocks.py --vault F:/Work/Obsidian
    python scripts/check_codeblocks.py --vault F:/Work/Obsidian --fix
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.codeblocks import codeblock_count_issue
from lib.translation_paths import source_for_translation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', type=Path, required=True)
    ap.add_argument('--fix', action='store_true',
                    help='Print slugs that need retranslation (for use with --force)')
    args = ap.parse_args()

    vault = args.vault.resolve()
    en_files = sorted(vault.rglob('*.en.md'))

    broken = []

    for en_path in en_files:
        zh_path = source_for_translation(en_path, vault)
        if not zh_path.exists():
            continue

        zh_text = zh_path.read_text(encoding='utf-8')
        en_text = en_path.read_text(encoding='utf-8')

        issues = []
        issue = codeblock_count_issue(zh_text, en_text)
        if issue:
            issues.append(issue)

        if issues:
            # Extract slug from frontmatter
            slug_match = re.search(r'^Slug:\s*(.+)$', zh_text, re.MULTILINE)
            slug = slug_match.group(1).strip() if slug_match else en_path.stem.replace('.en', '')
            broken.append((slug, en_path.relative_to(vault), issues))

    if not broken:
        print('✅ All .en.md files have matching code blocks.')
        return

    print(f'❌ Found {len(broken)} file(s) with code block mismatches:\n')
    for slug, rel_path, issues in broken:
        print(f'  {rel_path}')
        print(f'    Slug: {slug}')
        for issue in issues:
            print(f'    Issue: {issue}')
        print()

    if args.fix:
        print('\nRun these commands to retranslate:')
        for slug, _, _ in broken:
            print(f'  python scripts/translate.py --vault {args.vault} --only {slug} --force')


if __name__ == '__main__':
    main()
