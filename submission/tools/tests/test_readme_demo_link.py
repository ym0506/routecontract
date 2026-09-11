import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VIDEO_URL = "https://www.youtube.com/watch?v=pcgvNNxd1mM"


class ReadmeDemoLinkContractTest(unittest.TestCase):
    def test_reference_guides_start_with_current_example_and_support(self) -> None:
        for relative, guide, support_heading, java_support in (
            ("reference-guide.md", "first-project.md", "## v0.1 support boundary", "Java 17 or 21"),
            ("reference-guide.ko.md", "first-project.ko.md", "## v0.1 지원 범위", "Java 17 또는 21"),
        ):
            with self.subTest(page=relative):
                readme = (REPOSITORY_ROOT / "docs" / relative).read_text(encoding="utf-8")
                entry = readme.split("## Install 0.1.3", 1)[0]
                self.assertIn(f"({guide})", entry)
                self.assertIn(f"({guide}#try-in-your-browser)", entry)
                self.assertNotIn(VIDEO_URL, entry)
                self.assertNotIn("(#quick-start)", entry)
                support = readme.split(support_heading, 1)[1].split("\n## ", 1)[0]
                self.assertIn(java_support, support)
                self.assertIn("(java21-runtime-acceptance.md)", support)

    def test_main_readmes_keep_a_direct_public_demo_link(self) -> None:
        for relative, guide in (
            ("README.md", "docs/first-project.md"),
            ("README.ko.md", "docs/first-project.ko.md"),
        ):
            with self.subTest(page=relative):
                text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(f"({guide}#try-in-your-browser)", text)


if __name__ == "__main__":
    unittest.main()
