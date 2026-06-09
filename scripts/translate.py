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
import re
import shutil
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

=== RULE #1: CODE BLOCK INTEGRITY (HIGHEST PRIORITY) ===

Every fenced code block (``` ... ```) in the input MUST appear EXACTLY once in the output,
with the SAME opening fence (including language tag), SAME closing fence, and ALL original
lines preserved between them. Count the ``` fences in your output — it MUST match the input.

NEVER do any of these:
- Close a ``` fence early (before all code lines are included)
- Split one code block into multiple code blocks
- Move code lines outside of their ``` fences
- Drop the language tag (```bash, ```python, etc.)
- Add extra ``` fences that don't exist in the input

WRONG (broken code block):
  ```bash
  # Exploit Title: TextPattern CMS
  ```
  # Date: 2021/09/06          ← THIS LINE SHOULD BE INSIDE THE CODE BLOCK

CORRECT (intact code block):
  ```bash
  # Exploit Title: TextPattern CMS
  # Date: 2021/09/06
  ```

=== RULE #1b: STRUCTURAL INTEGRITY ===

The input is one CHUNK of a larger document. Preserve its structure exactly:
- Every heading (# ## ###) in the input MUST appear in the output at the same position
- Every list item (- item) MUST have content. NEVER output bare - with no text
- Every paragraph break in the input MUST remain in the output
- Do NOT merge multiple paragraphs into one
- Do NOT merge a heading with its following paragraph

=== RULE #1c: CODE BLOCK COMPLETENESS ===

For each code block in the input:
- The opening ``` (with language tag) and closing ``` MUST both appear in output
- ALL lines between them MUST be preserved (translated only if they are comments)
- Count your code block fences: input count MUST equal output count

=== RULE #2: TRANSLATION INSIDE CODE BLOCKS ===

For content INSIDE code blocks:
- Translate ONLY comment lines (lines starting with # or //) and inline comments
- Do NOT translate commands, variable names, function names, file paths, output, or any executable code
- Do NOT translate tool output, terminal responses, or log lines

=== RULE #3: GENERAL TRANSLATION ===

- Translate all Chinese text to natural, professional English
- Do NOT translate or modify [[wikilinks]] or ![[embeds]]
- Do NOT translate technical terms: CVE IDs, tool names, protocol names, ports, IPs, hostnames, hashes
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


def _get_translated_path(vault: Path, src: Path, move_dest: Path | None) -> Path | None:
    """Get the path where a translated .en.md file would be in the Translated/ directory."""
    dest_root = (move_dest or vault / "Translated").resolve()
    try:
        rel = src.relative_to(vault)
    except ValueError:
        return None
    return dest_root / rel.with_suffix(".en.md")


def validate_chunk(original: str, translated: str) -> bool:
    """Validate structural integrity of a translated chunk.

    Checks:
    1. Code block fence count matches (must both be even or both odd)
    2. Heading count matches

    Returns True if valid, False otherwise.
    """
    # 1. Code block fence count
    orig_fences = original.count("```")
    trans_fences = translated.count("```")
    if orig_fences % 2 == 0 and trans_fences % 2 != 0:
        return False
    if orig_fences > 0 and trans_fences == 0:
        return False

    # 2. Heading count
    orig_headings = len(re.findall(r"^#{1,3}\s", original, re.MULTILINE))
    trans_headings = len(re.findall(r"^#{1,3}\s", translated, re.MULTILINE))
    if orig_headings != trans_headings:
        return False

    return True


RETRY_PROMPT = (
    "Your previous response lost structural elements. "
    "Preserve ALL headings, code blocks, and list items exactly. "
    "Try again."
)


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
        total_tokens += tokens

        # Validate structural integrity, retry if broken
        max_retries = 2
        for attempt in range(max_retries):
            if validate_chunk(chunk, translated_text):
                break
            log.warning(
                f"  Chunk validation failed (attempt {attempt + 1}/{max_retries}), retrying..."
            )
            retry_system = SYSTEM_PROMPT + "\n\n" + RETRY_PROMPT
            translated_text, retry_tokens = client.translate_chunk(retry_system, chunk)
            total_tokens += retry_tokens
        else:
            # All retries exhausted — check one more time
            if not validate_chunk(chunk, translated_text):
                log.warning("  Chunk still invalid after retries, using original")
                translated_text = chunk

        translated_chunks.append(translated_text)

    translated_body = "\n\n".join(translated_chunks)

    # Build translated frontmatter
    translated_fm = dict(fm)
    translated_fm["lang"] = "en"
    translated_fm["source"] = src_path.name
    translated_fm["source_hash"] = src_hash
    translated_fm["translated_at"] = '"{}"'.format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    ap.add_argument(
        "--move-dest", type=Path, default=None,
        help="Destination for .en.md files (default: <vault>/Translated)",
    )
    ap.add_argument("--no-move", action="store_true", help="Keep .en.md files in vault")
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

    stats = {"translated": 0, "cached": 0, "failed": 0, "tokens": 0}
    move_dest = args.move_dest

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

        # Check cache: look in both source dir and Translated/ dir
        cached = False
        if not args.force:
            # Check next to source file first
            if en_path.exists():
                try:
                    en_fm, _ = read_note(en_path)
                    if en_fm.get("source_hash") == src_hash:
                        cached = True
                except Exception:
                    pass
            # Check in Translated/ directory
            if not cached:
                translated_path = _get_translated_path(vault, src, move_dest)
                if translated_path and translated_path.exists():
                    try:
                        en_fm, _ = read_note(translated_path)
                        if en_fm.get("source_hash") == src_hash:
                            cached = True
                            en_path = translated_path  # Update path for move step
                    except Exception:
                        pass
        if cached:
            log.info(f"  [CACHED] {src.relative_to(vault)}")
            stats["cached"] += 1
            continue

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
        f"failed={stats['failed']}, tokens={stats['tokens']}"
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
                f.write(f"| Tokens used | {stats['tokens']} |\n")
        except Exception as e:
            log.warning(f"Could not write GITHUB_STEP_SUMMARY: {e}")

    # 6. Move translated files (default: to <vault>/Translated)
    if not args.no_move:
        dest_root = (args.move_dest or vault / "Translated").resolve()
        en_files = sorted(vault.rglob("*.en.md"))
        # Exclude files already in dest
        en_files = [f for f in en_files if dest_root not in f.parents]
        moved = 0
        for src in en_files:
            rel = src.relative_to(vault)
            dst = dest_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved += 1
        log.info(f"Moved {moved} translated file(s) to {dest_root}")

    sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
