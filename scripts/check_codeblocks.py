#!/usr/bin/env python3
"""Check .en.md files for missing code blocks compared to their Chinese originals.

Usage:
    python scripts/check_codeblocks.py --vault F:/Work/Obsidian
    python scripts/check_codeblocks.py --vault F:/Work/Obsidian --fix
"""

import argparse
import re
import sys
from pathlib import Path

# Match opening fences: ```python, ```bash, ``` etc.
FENCE_OPEN = re.compile(r'^```(\w*)', re.MULTILINE)


def count_fenced_blocks(text: str) -> dict:
    """Return {lang: count} for all fenced code blocks."""
    counts: dict[str, int] = {}
    for m in FENCE_OPEN.finditer(text):
        lang = m.group(1).lower() or 'plain'
        counts[lang] = counts.get(lang, 0) + 1
    return counts


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
        zh_path = Path(str(en_path).replace('.en.md', '.md'))
        if not zh_path.exists():
            continue

        zh_text = zh_path.read_text(encoding='utf-8')
        en_text = en_path.read_text(encoding='utf-8')

        zh_counts = count_fenced_blocks(zh_text)
        en_counts = count_fenced_blocks(en_text)

        # Check if any language has fewer blocks in EN than ZH
        issues = []
        for lang, zh_n in zh_counts.items():
            en_n = en_counts.get(lang, 0)
            if en_n < zh_n:
                issues.append(f'{lang}: ZH={zh_n} EN={en_n}')

        if issues:
            # Extract slug from frontmatter
            slug_match = re.search(r'^Slug:\s*(.+)$', zh_text, re.MULTILINE)
            slug = slug_match.group(1).strip() if slug_match else en_path.stem.replace('.en', '')
            broken.append((slug, en_path.relative_to(vault), issues))

    if not broken:
        print('✅ All .en.md files have matching code blocks.')
        return

    print(f'❌ Found {len(broken)} file(s) with missing code blocks:\n')
    for slug, rel_path, issues in broken:
        print(f'  {rel_path}')
        print(f'    Slug: {slug}')
        for issue in issues:
            print(f'    Missing: {issue}')
        print()

    if args.fix:
        print('\nRun these commands to retranslate:')
        for slug, _, _ in broken:
            print(f'  python scripts/translate.py --vault {args.vault} --only {slug} --force')


if __name__ == '__main__':
    main()
