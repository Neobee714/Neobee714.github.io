#!/usr/bin/env python3
"""Obsidian vault translation script (ZH → EN).

Scans a vault for published posts, computes source hashes for caching,
and translates content via an OpenAI-compatible LLM API.

Usage:
    python scripts/translate.py --vault F:/Work/Obsidian --dry-run
    python scripts/translate.py --vault ./vault --only htb-bruno
    python scripts/translate.py --vault ./vault --force
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env file if present (for local development)
def _load_dotenv():
    """Load .env file from project root or scripts/ directory."""
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

# Ensure scripts/ is importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.frontmatter import read_note, write_note
from lib.hash_util import compute_source_hash
from lib.chunker import chunk_by_headings
from lib.llm_client import LlmClient

log = logging.getLogger("translate")

# --- System Prompt (design §7.5) ---

SYSTEM_PROMPT = """\
You are a professional technical translator specializing in cybersecurity and CTF writeups.
Translate the following Chinese Markdown content to English.

Rules:
- Translate all Chinese text to natural, professional English
- CRITICAL: Preserve ALL Markdown formatting EXACTLY as-is:
  - Code blocks MUST keep their opening ``` and closing ``` fences
  - Code block language tags (```python, ```bash, etc.) MUST be preserved
  - Do NOT convert code blocks to plain text
  - Do NOT remove or modify ``` fences under any circumstances
- For content INSIDE code blocks (``` ... ```):
  - Translate ONLY comments (lines starting with # or //, or inline comments after code)
  - Do NOT translate commands, variable names, function names, file paths, or any executable code
  - Do NOT translate tool output, terminal responses, or log lines
- Do NOT translate or modify [[wikilinks]] or ![[embeds]]
- Do NOT translate technical terms: CVE IDs, tool names (nmap, gobuster, etc.), protocol names, port numbers, IP addresses, hostnames, hashes, exploit names
- Do NOT include frontmatter in the output (no --- blocks)
- Keep the same paragraph and section structure
- Preserve all URLs, file paths, and command syntax exactly

Return ONLY the translated content between <TRANSLATED> and </TRANSLATED> tags.
"""


def is_publishable_original(path: Path) -> bool:
    """Check if a note is a publishable original (not a translation, not a template).

    Args:
        path: Path to the .md file.

    Returns:
        True if the note should be translated.
    """
    # Skip translation files
    if path.name.endswith(".en.md"):
        return False
    # Skip template files
    if "/Templates/" in str(path).replace("\\", "/"):
        return False
    try:
        fm, _ = read_note(path)
    except Exception:
        return False
    # Must have 发布: true (strict boolean check)
    published = fm.get("发布")
    if published is not True and str(published).lower() not in ("true", "yes", "是"):
        return False
    # Must have a Slug
    if not fm.get("Slug"):
        return False
    # Skip drafts (状态: 进行中)
    status = fm.get("状态", "")
    if status in ("进行中", "draft"):
        return False
    return True


def get_slug(path: Path) -> str:
    """Extract the Slug from a note's frontmatter.

    Args:
        path: Path to the .md file.

    Returns:
        The Slug value, or empty string if not found.
    """
    try:
        fm, _ = read_note(path)
        return fm.get("Slug", "")
    except Exception:
        return ""


def translate_note(
    client: LlmClient, src_path: Path, src_hash: str
) -> tuple[dict, str, int]:
    """Translate a single note: chunk body, translate each chunk, assemble output.

    Args:
        client: The LLM client instance.
        src_path: Path to the source .md file.
        src_hash: Pre-computed source hash.

    Returns:
        A tuple of (translated_frontmatter, translated_body, total_tokens).
    """
    fm, body = read_note(src_path)

    # Chunk the body for translation
    chunks = chunk_by_headings(body)
    translated_chunks = []
    total_tokens = 0

    for chunk in chunks:
        translated_text, tokens = client.translate_chunk(SYSTEM_PROMPT, chunk)
        translated_chunks.append(translated_text)
        total_tokens += tokens

    translated_body = "\n\n".join(translated_chunks)

    # Build translated frontmatter
    translated_fm = dict(fm)
    translated_fm["lang"] = "en"
    translated_fm["source"] = src_path.name
    translated_fm["source_hash"] = src_hash
    translated_fm["translated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # Translate 简介 (summary) if present
    jianjie = str(fm.get("简介", "")).strip()
    if jianjie:
        try:
            summary_prompt = "Translate the following Chinese text to English. Return only the translated text, nothing else."
            translated_summary, summary_tokens = client.translate_chunk(summary_prompt, jianjie)
            translated_fm["简介"] = translated_summary.strip()
            total_tokens += summary_tokens
        except Exception as e:
            log.warning(f"Failed to translate 简介: {e}")
            # Keep original if translation fails

    return translated_fm, translated_body, total_tokens


def main() -> None:
    """Main entry point for the translation script."""
    ap = argparse.ArgumentParser(
        description="Translate published Obsidian notes from Chinese to English."
    )
    ap.add_argument(
        "--vault",
        type=Path,
        required=True,
        help="Path to vault root (e.g. ./vault or F:/Work/Obsidian)",
    )
    ap.add_argument("--force", action="store_true", help="Ignore cache, retranslate all")
    ap.add_argument("--only", type=str, help="Only translate this slug")
    ap.add_argument("--dry-run", action="store_true", help="List files without translating")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    vault = args.vault.resolve()
    if not vault.is_dir():
        log.error(f"Vault path does not exist: {vault}")
        sys.exit(1)

    # 1. Scan vault for published originals
    md_files = list(vault.rglob("*.md"))
    originals = [f for f in md_files if is_publishable_original(f)]
    log.info(f"Found {len(originals)} publishable originals")

    # 2. Filter by --only
    if args.only:
        originals = [f for f in originals if get_slug(f) == args.only]
        log.info(f"Filtered to {len(originals)} file(s) matching slug '{args.only}'")

    stats = {"translated": 0, "cached": 0, "failed": 0, "skipped": 0, "tokens": 0}

    # In dry-run mode we don't need the LLM client
    client = None
    if not args.dry_run:
        try:
            client = LlmClient.from_env()
        except ValueError as e:
            log.error(f"Cannot initialize LLM client: {e}")
            sys.exit(1)

    # 3. Process each file
    for src in originals:
        fm, body = read_note(src)
        src_hash = compute_source_hash(fm, body)
        en_path = src.with_suffix(".en.md")

        # Check cache
        if not args.force and en_path.exists():
            try:
                en_fm, _ = read_note(en_path)
                if en_fm.get("source_hash") == src_hash:
                    log.info(f"  [CACHED] {src.relative_to(vault)}")
                    stats["cached"] += 1
                    continue
            except Exception:
                pass  # If we can't read the en file, retranslate

        # Dry-run: just report what would be translated
        if args.dry_run:
            log.info(f"  [WOULD TRANSLATE] {src.relative_to(vault)}")
            stats["translated"] += 1
            continue

        # Translate
        log.info(f"  [TRANSLATE] {src.relative_to(vault)}")
        try:
            translated_fm, translated_body, tokens = translate_note(
                client, src, src_hash  # type: ignore[arg-type]
            )
            write_note(en_path, translated_fm, translated_body)
            stats["translated"] += 1
            stats["tokens"] += tokens
        except Exception as e:
            log.error(f"  [FAIL] {src.relative_to(vault)}: {e}")
            stats["failed"] += 1
            # Don't overwrite existing .en.md on failure

    # 4. Print summary
    log.info(
        f"Summary: translated={stats['translated']}, cached={stats['cached']}, "
        f"failed={stats['failed']}, skipped={stats['skipped']}, tokens={stats['tokens']}"
    )

    # 5. Write GITHUB_STEP_SUMMARY if available
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("## 🌐 Translation Summary\n\n")
                f.write(f"| Metric | Count |\n|--------|-------|\n")
                f.write(f"| Translated | {stats['translated']} |\n")
                f.write(f"| Cached | {stats['cached']} |\n")
                f.write(f"| Failed | {stats['failed']} |\n")
                f.write(f"| Skipped | {stats['skipped']} |\n")
                f.write(f"| Tokens used | {stats['tokens']} |\n")
        except Exception as e:
            log.warning(f"Could not write GITHUB_STEP_SUMMARY: {e}")

    sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
