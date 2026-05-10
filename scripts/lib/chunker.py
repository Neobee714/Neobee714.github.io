"""Split long Markdown text into chunks at heading boundaries.

Splits at h1/h2 boundaries (lines starting with `# ` or `## `).
Short texts (< max_chars) are returned as a single chunk.
Each chunk is self-contained and includes the heading it starts with.
"""

import re
from typing import List

# Matches lines that start with # or ## (h1/h2 headings)
_HEADING_SPLIT = re.compile(r"(?=^#{1,2}\s)", re.MULTILINE)


def chunk_by_headings(body: str, max_chars: int = 4000) -> List[str]:
    """Split body text into chunks at h1/h2 heading boundaries.

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
        if len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                chunks.append(current)
            current = part

    if current:
        chunks.append(current)

    return chunks
