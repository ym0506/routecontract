import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VIDEO_URL = "https://www.youtube.com/watch?v=pcgvNNxd1mM"


class ReadmeDemoLinkContractTest(unittest.TestCase):
    def test_reference_guides_keep_the_public_demo_before_pinned_quick_start(self) -> None:
        for path, exact_link in (
            (
                REPOSITORY_ROOT / "docs" / "reference-guide.ko.md",
                f"[2분 54초 시연 영상 보기]({VIDEO_URL})",
            ),
            (
                REPOSITORY_ROOT / "docs" / "reference-guide.md",
                f"[Watch the 2:54 demo]({VIDEO_URL})",
            ),
        ):
            with self.subTest(path=path):
                readme = path.read_text(encoding="utf-8")
                self.assertEqual(1, readme.count(VIDEO_URL))
                self.assertEqual(1, readme.count(exact_link))
                self.assertLess(
                    readme.index(exact_link),
                    readme.index("submission/assets/baseline-candidate.png"),
                )
                self.assertLess(
                    readme.index("submission/assets/baseline-candidate.png"),
                    readme.index("## Quick Start"),
                )

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
