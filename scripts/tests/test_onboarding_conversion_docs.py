#!/usr/bin/env python3
"""Contract tests for the first-screen assisted-pilot onboarding path."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KOREAN_README = REPOSITORY_ROOT / "README.md"
ENGLISH_README = REPOSITORY_ROOT / "README.en.md"
INTEGRATION_GUIDE = REPOSITORY_ROOT / "docs" / "first-integration.md"

DISCUSSION_REPLY = """\
> ```text
> interested
> repository: https://github.com/OWNER/REPOSITORY
> test: path/to/ExistingShardingSphereIntegrationTest.java
> ```"""


class OnboardingConversionDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.korean = KOREAN_README.read_text(encoding="utf-8")
        cls.english = ENGLISH_README.read_text(encoding="utf-8")
        cls.guide = INTEGRATION_GUIDE.read_text(encoding="utf-8")

    def test_bilingual_first_screen_has_exact_three_line_reply(self) -> None:
        for name, text, quick_start in (
            ("Korean", self.korean, "## Quick Start"),
            ("English", self.english, "## Quick Start"),
        ):
            with self.subTest(readme=name):
                self.assertEqual(1, text.count(DISCUSSION_REPLY))
                self.assertLess(text.index(DISCUSSION_REPLY), text.index(quick_start))
                self.assertLessEqual(
                    text[: text.index(DISCUSSION_REPLY)].count("\n") + 1,
                    24,
                    "the copy/paste reply must remain on the first screen",
                )

                match = re.search(
                    r"> ```text\n(?P<body>(?:> .*\n){3})> ```",
                    DISCUSSION_REPLY,
                )
                self.assertIsNotNone(match)
                payload = [
                    line.removeprefix("> ")
                    for line in match.group("body").splitlines()
                ]
                self.assertEqual(
                    [
                        "interested",
                        "repository: https://github.com/OWNER/REPOSITORY",
                        "test: path/to/ExistingShardingSphereIntegrationTest.java",
                    ],
                    payload,
                )

    def test_bilingual_first_screen_warns_against_public_sensitive_data(self) -> None:
        required = {
            "Korean": (
                self.korean,
                "공개 답글에는",
                ("원문 SQL", "bind 값", "JDBC URL", "credentials", "실제 topology", "full log"),
            ),
            "English": (
                self.english,
                "Do not put",
                ("raw SQL", "bind values", "JDBC URLs", "credentials", "real topology", "full logs"),
            ),
        }
        for name, (text, warning_start, fragments) in required.items():
            with self.subTest(readme=name):
                first_screen = text[: text.index("## Quick Start")]
                warning_offset = first_screen.index(warning_start)
                warning = first_screen[warning_offset:]
                for fragment in fragments:
                    self.assertIn(fragment, warning)

    def test_reference_starts_with_one_shared_four_step_path(self) -> None:
        heading = "## Four-step supported path for Gradle or Maven"
        self.assertEqual(1, self.guide.count(heading))
        self.assertLess(
            self.guide.index(heading),
            self.guide.index("## 1. Verify the published demo first"),
        )
        section = self.guide[
            self.guide.index(heading) : self.guide.index(
                "## 1. Verify the published demo first"
            )
        ]
        numbered_steps = re.findall(r"(?m)^\d+\. \*\*(.+?)\*\*", section)
        self.assertEqual(
            [
                "Check fit and choose one operation.",
                "Install and isolate one build lane.",
                "Capture one candidate without approving it.",
                "Review, approve, and gate separately.",
            ],
            numbered_steps,
        )
        compact_section = " ".join(section.split())

        for required in (
            "Java 17",
            "exactly ShardingSphere-JDBC 5.5.3",
            "synchronous non-batch `PreparedStatement`",
            "Stop",
            "Gradle Groovy",
            "Gradle Kotlin DSL",
            "Maven 3.9.14",
            "existing business assertion",
            "never creates or replaces an approved baseline",
            "explicit budgets",
            "required CI check",
        ):
            self.assertIn(required, compact_section)

        self.assertIn(
            "An external-user result exists only when an external team or developer applies the RouteContract dependency, a human-approved exact baseline, and the candidate check to a representative operation in their own repository, and that check succeeds in the repository's upstream public CI",
            compact_section,
        )
        self.assertIn(
            "Assisted help or a private first-pass patch is allowed; an owner-run, same-checkout, local-only, or draft result is insufficient",
            compact_section,
        )
        self.assertIn(
            "does not establish adoption, endorsement, production use, performance, or security",
            compact_section,
        )


if __name__ == "__main__":
    unittest.main()
