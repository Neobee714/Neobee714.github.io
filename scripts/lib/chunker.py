"""Split long Markdown text into chunks at heading boundaries.

Splits at h1/h2 boundaries (lines starting with `# ` or `## `).
Short texts (< max_chars) are returned as a single chunk.
Each chunk is self-contained and includes the heading it starts with.
"""

import re
from typing import List

# Matches lines that start with #, ## or ### (h1/h2/h3 headings)
_HEADING_SPLIT = re.compile(r"(?=^#{1,3}\s)", re.MULTILINE)


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
        return [body]

    # Split at heading boundaries (lookahead keeps the heading with its section)
    parts = _HEADING_SPLIT.split(body)

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

    return chunks


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
