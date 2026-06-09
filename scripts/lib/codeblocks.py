"""Markdown fenced code block parsing helpers."""

import re

FENCE = re.compile(r"^(?:>\s*)?```([^\s`]*)")


def fenced_blocks(text: str) -> list[str]:
    """Return opening fence language tags for complete fenced code blocks."""
    blocks: list[str] = []
    in_block = False

    for line in text.splitlines():
        match = FENCE.match(line)
        if not match:
            continue

        if not in_block:
            blocks.append((match.group(1) or "plain").lower())
            in_block = True
        else:
            in_block = False

    return blocks


def codeblock_count_issue(source_text: str, translated_text: str) -> str | None:
    """Return a human-readable issue when translated code blocks diverge."""
    source_blocks = fenced_blocks(source_text)
    translated_blocks = fenced_blocks(translated_text)
    if len(translated_blocks) != len(source_blocks):
        return f"blocks: ZH={len(source_blocks)} EN={len(translated_blocks)}"
    if translated_blocks != source_blocks:
        return (
            "languages: "
            f"ZH={','.join(source_blocks)} EN={','.join(translated_blocks)}"
        )
    return None
