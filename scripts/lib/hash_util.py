"""Source hash computation for translation caching.

Computes a stable SHA-256 hash from selected frontmatter fields + body content.
Does NOT include mtime or other volatile metadata, ensuring the same file
always produces the same hash regardless of when it's computed.
"""

import hashlib
from pathlib import Path
from typing import Union

from .frontmatter import read_note

# Frontmatter keys that affect translation output
_KEYS_TO_HASH = [
    "简介",
    "tags",
    "类型",
]


def compute_source_hash(fm: dict, body: str) -> str:
    """Compute a stable SHA-256 hash from frontmatter fields and body.

    Args:
        fm: Frontmatter metadata dict.
        body: Markdown body content.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    hashable = {k: fm.get(k) for k in _KEYS_TO_HASH}
    m = hashlib.sha256()
    m.update(repr(sorted(hashable.items())).encode("utf-8"))
    m.update(b"\n---\n")
    m.update(body.encode("utf-8"))
    return m.hexdigest()


def compute_source_hash_from_file(path: Union[str, Path]) -> str:
    """Convenience: read a note file and compute its source hash.

    Args:
        path: Path to the .md file.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    fm, body = read_note(path)
    return compute_source_hash(fm, body)
