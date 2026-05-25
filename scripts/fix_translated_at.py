#!/usr/bin/env python3
"""Fix translated_at field in .en.md files — wrap bare ISO timestamps in quotes."""
import re
import sys
from pathlib import Path

vault = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("F:/Work/Obsidian")

# Match unquoted ISO datetime in frontmatter
PATTERN = re.compile(r'^(translated_at:\s*)(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s*$',
                     re.MULTILINE)

fixed = 0
for en_path in vault.rglob("*.en.md"):
    text = en_path.read_text(encoding="utf-8")
    new_text, n = PATTERN.subn(r'\1"\2"', text)
    if n:
        en_path.write_text(new_text, encoding="utf-8")
        fixed += 1
        print(f"Fixed: {en_path.relative_to(vault)}")

print(f"\nTotal fixed: {fixed}")
