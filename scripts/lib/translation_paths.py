"""Helpers for mapping translated markdown files back to source notes."""

from pathlib import Path


def source_for_translation(en_path: Path, vault: Path) -> Path:
    """Return the expected Chinese source path for a translated .en.md file."""
    en_path = Path(en_path).resolve()
    vault = Path(vault).resolve()

    same_dir = Path(str(en_path).replace(".en.md", ".md"))
    if same_dir.exists():
        return same_dir

    translated_root = vault / "Translated"
    try:
        rel = en_path.relative_to(translated_root)
    except ValueError:
        return same_dir

    return Path(str(vault / rel).replace(".en.md", ".md"))
