"""Frontmatter read/write utilities for Obsidian notes.

Uses python-frontmatter library. Preserves Chinese field names (发布, 简介, etc.)
and ensures lossless round-trip (same content in = same content out).
"""

from pathlib import Path
from typing import Union

import frontmatter


def read_note(path: Union[str, Path]) -> tuple[dict, str]:
    """Read an Obsidian note and return (frontmatter_dict, body_string).

    Args:
        path: Path to the .md file.

    Returns:
        A tuple of (metadata dict, body text).
    """
    path = Path(path)
    post = frontmatter.load(path, encoding="utf-8")
    return dict(post.metadata), post.content


def write_note(path: Union[str, Path], fm: dict, body: str) -> None:
    """Write a note with frontmatter and body content.

    Args:
        path: Destination file path.
        fm: Frontmatter metadata dict.
        body: Markdown body content.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **fm)
    content = frontmatter.dumps(post)
    # Ensure UTF-8 encoding is used explicitly
    path.write_bytes(content.encode("utf-8"))
