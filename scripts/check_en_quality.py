#!/usr/bin/env python3
"""Check .en.md files for quality issues:
1. Corrupted frontmatter (garbled Chinese field names)
2. Code block fence mismatch compared to original
3. <SOURCE> tags leaked into content
4. translated_at is unquoted ISO datetime (YAML parses as object)

Usage:
    python scripts/check_en_quality.py --vault F:/Work/Obsidian
    python scripts/check_en_quality.py --vault F:/Work/Obsidian --fix  # delete bad files
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.codeblocks import codeblock_count_issue
from lib.translation_paths import source_for_translation

GARBLED = re.compile(r'[\u9489-\u9fff\u5c0f-\u5c1f]{2,}:')  # garbled CJK field names
UNQUOTED_TS = re.compile(r'^translated_at:\s+\d{4}-\d{2}-\d{2}T', re.MULTILINE)
SOURCE_TAG = re.compile(r'<SOURCE>')


def check_file(en_path: Path, zh_path: Path) -> list[str]:
    issues = []
    try:
        en_text = en_path.read_text(encoding='utf-8')
    except Exception as e:
        return [f'Cannot read: {e}']

    # 1. Garbled frontmatter
    if GARBLED.search(en_text):
        issues.append('garbled frontmatter (encoding corruption)')

    # 2. <SOURCE> tag leaked
    if SOURCE_TAG.search(en_text):
        issues.append('<SOURCE> tag leaked into content')

    # 3. Unquoted translated_at
    if UNQUOTED_TS.search(en_text):
        issues.append('unquoted translated_at (YAML will parse as object)')

    # 4. Code block mismatch
    if zh_path.exists():
        zh_text = zh_path.read_text(encoding='utf-8')
        issue = codeblock_count_issue(zh_text, en_text)
        if issue:
            issues.append(f'code block mismatch: {issue}')

    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', type=Path, required=True)
    ap.add_argument('--fix', action='store_true', help='Delete bad .en.md files for regeneration')
    args = ap.parse_args()

    vault = args.vault.resolve()
    en_files = sorted(vault.rglob('*.en.md'))

    bad = []
    for en_path in en_files:
        zh_path = source_for_translation(en_path, vault)
        issues = check_file(en_path, zh_path)
        if issues:
            slug_match = re.search(r'^Slug:\s*(.+)$',
                                   en_path.read_text(encoding='utf-8', errors='replace'),
                                   re.MULTILINE)
            slug = slug_match.group(1).strip() if slug_match else en_path.stem
            bad.append((slug, en_path, issues))

    if not bad:
        print('✅ All .en.md files look good.')
        return

    print(f'❌ Found {len(bad)} file(s) with issues:\n')
    slugs_to_retranslate = []
    for slug, en_path, issues in bad:
        print(f'  {en_path.relative_to(vault)}')
        for issue in issues:
            print(f'    • {issue}')
        slugs_to_retranslate.append(slug)
        if args.fix:
            en_path.unlink()
            print(f'    → DELETED (will be regenerated)')
        print()

    print(f'\nSlugs needing retranslation ({len(slugs_to_retranslate)}):')
    for slug in slugs_to_retranslate:
        print(f'  {slug}')

    if not args.fix:
        print('\nRun with --fix to delete bad files and allow regeneration.')
    else:
        print('\nDeleted bad files. Now run:')
        print(f'  python scripts/translate.py --vault {args.vault}')
        print('to regenerate them.')


if __name__ == '__main__':
    main()
