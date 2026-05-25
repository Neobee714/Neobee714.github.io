"""Split long Markdown text into chunks at heading boundaries.

Splits at h1/h2 boundaries (lines starting with `# ` or `## `).
Short texts (< max_chars) are returned as a single chunk.
Each chunk is self-contained and includes the heading it starts with.
"""

import re
from typing import List

# Matches lines that start with #, ## or ### (h1/h2/h3 headings)
_HEADING_SPLIT = re.compile(r"(?=^#{1,3}\s)", re.MULTILINE)

# Matches a fenced code block opening line: ``` optionally followed by a language tag
_CODE_FENCE_OPEN = re.compile(r"^```")


def _protect_code_blocks(text: str):
    """Replace code blocks with placeholders to prevent heading-split mis-detection.

    Uses line-by-line parsing instead of a single regex so that unclosed
    code blocks don't swallow everything after them.

    Returns (protected_text, mapping) where mapping maps placeholder -> original block.
    """
    mapping: dict[str, str] = {}
    counter = 0
    lines = text.split("\n")

    result_lines: list[str] = []
    in_code = False
    code_lines: list[str] = []

    for line in lines:
        if not in_code:
            if _CODE_FENCE_OPEN.match(line):
                # Start of a code block
                in_code = True
                code_lines = [line]
            else:
                result_lines.append(line)
        else:
            code_lines.append(line)
            # Closing fence: ``` on its own (with optional trailing whitespace)
            if re.match(r"^```\s*$", line):
                in_code = False
                key = f"__CODE_BLOCK_{counter}__"
                mapping[key] = "\n".join(code_lines)
                counter += 1
                result_lines.append(key)
                code_lines = []

    # Unclosed code block at end of file — auto-close it
    if in_code and code_lines:
        code_lines.append("```")
        key = f"__CODE_BLOCK_{counter}__"
        mapping[key] = "\n".join(code_lines)
        counter += 1
        result_lines.append(key)

    return "\n".join(result_lines), mapping


def _restore_code_blocks(text: str, mapping: dict[str, str]) -> str:
    """Restore placeholders back to original code blocks."""
    for key, block in mapping.items():
        text = text.replace(key, block)
    return text


def _clean_list_blank_lines(text: str) -> str:
    """Remove blank lines between consecutive list items.

    Converts:
        - item1
        (blank)
        - item2
    Into:
        - item1
        - item2

    Skips content inside code block placeholders.
    """
    lines = text.split("\n")
    result: list[str] = []
    for i, line in enumerate(lines):
        # Skip if this is a code block placeholder
        if line.strip().startswith("__CODE_BLOCK_"):
            result.append(line)
            continue

        # If this is a blank line and the next line is a list item, skip it
        if not line.strip() and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.startswith("- ") or next_line.startswith("* ") or re.match(r"\d+\.\s", next_line):
                continue

        result.append(line)
    return "\n".join(result)


def chunk_by_headings(body: str, max_chars: int = 2000) -> List[str]:
    """Split body text into chunks at h1/h2/h3 heading boundaries.

    Args:
        body: The Markdown body text to split.
        max_chars: Maximum characters per chunk. Short texts below this
                   threshold are returned as a single chunk.

    Returns:
        A list of text chunks. Each chunk includes its heading (if any).
    """
    if len(body) <= max_chars:
        return [_clean_list_blank_lines(body)]

    # Protect code blocks so # comments inside them aren't mistaken for headings
    protected, code_map = _protect_code_blocks(body)

    # Split at heading boundaries (lookahead keeps the heading with its section)
    parts = _HEADING_SPLIT.split(protected)

    chunks: List[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        # If a single part exceeds max_chars, force-split by paragraphs
        if len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            para_chunks = _split_by_paragraphs(part, max_chars)
            chunks.extend(para_chunks)
        elif len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                chunks.append(current)
            current = part

    if current:
        chunks.append(current)

    # Restore code blocks in each chunk and clean list blank lines
    return [_clean_list_blank_lines(_restore_code_blocks(c, code_map)) for c in chunks]


def _split_by_paragraphs(text: str, max_chars: int) -> List[str]:
    """Fallback: split a long section by double-newline paragraphs."""
    paragraphs = re.split(r'\n\n+', text)
    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        if not para.strip():
            continue
        if len(current) + len(para) + 2 <= max_chars:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    return chunks
