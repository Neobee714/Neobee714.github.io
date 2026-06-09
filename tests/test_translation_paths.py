import tempfile
import unittest
from pathlib import Path

from scripts.lib.translation_paths import source_for_translation


class TranslationPathTests(unittest.TestCase):
    def test_translated_tree_maps_back_to_source_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            zh = vault / "SecNotes" / "topic" / "demo.md"
            en = vault / "Translated" / "SecNotes" / "topic" / "demo.en.md"
            zh.parent.mkdir(parents=True)
            en.parent.mkdir(parents=True)
            zh.write_text("---\nSlug: demo\n---\nbody", encoding="utf-8")
            en.write_text("---\nSlug: demo\n---\nbody", encoding="utf-8")

            self.assertEqual(source_for_translation(en, vault), zh)

    def test_same_directory_translation_still_maps_to_neighbor(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            zh = vault / "SecNotes" / "demo.md"
            en = vault / "SecNotes" / "demo.en.md"
            zh.parent.mkdir(parents=True)
            zh.write_text("---\nSlug: demo\n---\nbody", encoding="utf-8")
            en.write_text("---\nSlug: demo\n---\nbody", encoding="utf-8")

            self.assertEqual(source_for_translation(en, vault), zh)


if __name__ == "__main__":
    unittest.main()
