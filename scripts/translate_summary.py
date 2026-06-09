#!/usr/bin/env python3
"""Translate only the 简介 (summary) field in existing .en.md files.

Usage:
    python scripts/translate_summary.py --vault F:/Work/Obsidian
    python scripts/translate_summary.py --vault F:/Work/Obsidian --only htb-bruno
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.frontmatter import read_note, write_note
from lib.llm_client import LlmClient
from lib.translation_paths import source_for_translation

log = logging.getLogger("translate_summary")

SUMMARY_PROMPT = "Translate the following Chinese text to English. Return only the translated text, nothing else."


def _load_dotenv():
    for env_path in [
        Path(__file__).resolve().parent.parent / '.env',
        Path(__file__).resolve().parent / '.env',
    ]:
        if env_path.exists():
            with open(env_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            break

_load_dotenv()


def main():
    ap = argparse.ArgumentParser(description="Translate 简介 field in .en.md files.")
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--only", type=str, help="Only process this slug")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    vault = args.vault.resolve()
    en_files = list(vault.rglob("*.en.md"))
    log.info(f"Found {len(en_files)} .en.md files")

    if args.only:
        en_files = [f for f in en_files if args.only in f.stem]
        log.info(f"Filtered to {len(en_files)} file(s)")

    client = None
    if not args.dry_run:
        client = LlmClient.from_env()

    updated = skipped = failed = missing_sources = 0

    for en_path in en_files:
        # Read the original Chinese file to get the 简介
        zh_path = source_for_translation(en_path, vault)
        if not zh_path.exists():
            missing_sources += 1
            skipped += 1
            continue

        try:
            zh_fm, _ = read_note(zh_path)
            jianjie = str(zh_fm.get("简介", "")).strip()
        except Exception as e:
            log.warning(f"Cannot read source {zh_path}: {e}")
            continue

        if not jianjie:
            skipped += 1
            continue

        # Check if already translated (not Chinese)
        en_fm, en_body = read_note(en_path)
        current = str(en_fm.get("简介", "")).strip()

        # Simple heuristic: if current 简介 contains Chinese chars, needs translation
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in current)
        if not has_chinese and current:
            log.info(f"  [SKIP] already translated: {en_path.name}")
            skipped += 1
            continue

        if args.dry_run:
            log.info(f"  [WOULD TRANSLATE] {en_path.name}: {jianjie[:50]}...")
            updated += 1
            continue

        try:
            translated, _ = client.translate_chunk(SUMMARY_PROMPT, jianjie)
            en_fm["简介"] = translated.strip()
            write_note(en_path, en_fm, en_body)
            log.info(f"  [DONE] {en_path.name}")
            updated += 1
        except Exception as e:
            log.error(f"  [FAIL] {en_path.name}: {e}")
            failed += 1

    if missing_sources:
        log.warning(
            f"Skipped {missing_sources} .en.md file(s) whose source note was not found"
        )

    log.info(f"Summary: updated={updated}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
