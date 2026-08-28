import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VIDEO_URL = "https://www.youtube.com/watch?v=pcgvNNxd1mM"


class ReadmeDemoLinkContractTest(unittest.TestCase):
    def test_readmes_link_the_public_demo_before_quick_start(self) -> None:
        for path, exact_link in (
            (
                REPOSITORY_ROOT / "README.md",
                f"[2분 54초 시연 영상 보기]({VIDEO_URL})",
            ),
            (
                REPOSITORY_ROOT / "README.en.md",
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


if __name__ == "__main__":
    unittest.main()
