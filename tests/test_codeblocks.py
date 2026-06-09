import unittest

from scripts.lib.codeblocks import codeblock_count_issue, fenced_blocks


class CodeBlockParserTests(unittest.TestCase):
    def test_counts_opening_fences_only(self):
        text = "```bash\necho hi\n```\n\n```\nplain\n```"

        self.assertEqual(fenced_blocks(text), ["bash", "plain"])

    def test_handles_obsidian_callout_blockquote_fences(self):
        text = "> [!tip]\n> ```bash\n> whoami\n> ```\n"

        self.assertEqual(fenced_blocks(text), ["bash"])

    def test_reports_when_translation_has_fewer_blocks(self):
        zh = "```bash\necho one\n```\n\n```bash\necho two\n```"
        en = "```bash\necho one\n```"

        self.assertEqual(codeblock_count_issue(zh, en), "blocks: ZH=2 EN=1")

    def test_reports_when_translation_has_extra_blocks(self):
        zh = "```bash\necho one\n```"
        en = "```bash\necho one\n```\n\n```python\nprint('extra')\n```"

        self.assertEqual(codeblock_count_issue(zh, en), "blocks: ZH=1 EN=2")

    def test_reports_when_translation_changes_block_languages(self):
        zh = "```bash\necho one\n```\n\n```python\nprint('two')\n```"
        en = "```bash\necho one\n```\n\n```\nprint('two')\n```"

        self.assertEqual(
            codeblock_count_issue(zh, en),
            "languages: ZH=bash,python EN=bash,plain",
        )


if __name__ == "__main__":
    unittest.main()
