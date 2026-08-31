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
> Repository: https://github.com/OWNER/REPOSITORY
> Build: Gradle or Maven
> ```"""

FIRST_SCREEN_LAST_SOURCE_LINE = 30


class OnboardingConversionDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.korean = KOREAN_README.read_text(encoding="utf-8")
        cls.english = ENGLISH_README.read_text(encoding="utf-8")
        cls.guide = INTEGRATION_GUIDE.read_text(encoding="utf-8")

    def test_bilingual_first_screen_has_exact_three_line_reply(self) -> None:
        for name, text in (
            ("Korean", self.korean),
            ("English", self.english),
        ):
            with self.subTest(readme=name):
                self.assertEqual(1, text.count(DISCUSSION_REPLY))
                reply_start = text.index(DISCUSSION_REPLY)
                reply_end = reply_start + len(DISCUSSION_REPLY)
                warning_end = text.index("personal info", reply_end) + len(
                    "personal info"
                )
                self.assertLess(reply_end, warning_end)
                self.assertLessEqual(
                    text[:reply_end].count("\n") + 1,
                    FIRST_SCREEN_LAST_SOURCE_LINE,
                    "the complete copy/paste reply must remain on the first screen",
                )
                self.assertLessEqual(
                    text[:warning_end].count("\n") + 1,
                    FIRST_SCREEN_LAST_SOURCE_LINE,
                    "the complete sensitive-data warning must remain on the first screen",
                )
                policy_block = text[: text.index("[Apache ShardingSphere-JDBC]")]
                self.assertLessEqual(
                    policy_block.rstrip().count("\n") + 1,
                    FIRST_SCREEN_LAST_SOURCE_LINE,
                    "the complete assisted-pilot policy must remain on the first screen",
                )

                match = re.search(
                    r"> ```text\n(?P<body>(?:> .*\n){3})> ```",
                    text,
                )
                self.assertIsNotNone(match)
                payload = [
                    line.removeprefix("> ")
                    for line in match.group("body").splitlines()
                ]
                self.assertEqual(
                    [
                        "interested",
                        "Repository: https://github.com/OWNER/REPOSITORY",
                        "Build: Gradle or Maven",
                    ],
                    payload,
                )
                first_screen = text[:warning_end]
                self.assertNotIn("> repository:", first_screen)
                self.assertNotIn("> test:", first_screen)

    def test_bilingual_first_screen_warns_against_public_sensitive_data(self) -> None:
        required_fragments = (
            "credentials",
            "raw SQL",
            "binds",
            "JDBC URLs",
            "customer data",
            "private topology",
            "hostnames",
            "absolute paths",
            "logs",
            "screenshots",
            "personal info",
        )
        for name, text, warning_prefix, warning_suffix in (
            (
                "Korean",
                self.korean,
                "Discussion #34나 비공개 채널로 credentials",
                "personal info를 보내지 마세요",
            ),
            (
                "English",
                self.english,
                "Do not send credentials",
                "personal info in Discussion #34 or through a private channel",
            ),
        ):
            with self.subTest(readme=name):
                first_screen = text[: text.index("[Apache ShardingSphere-JDBC]")]
                warning_offset = first_screen.index("credentials")
                warning = first_screen[warning_offset:]
                for fragment in required_fragments[:-1]:
                    self.assertIn(fragment, warning)
                self.assertIn("personal info", warning)
                self.assertIn(warning_prefix, first_screen)
                self.assertIn(warning_suffix, first_screen)

    def test_bilingual_assisted_pilot_policy_is_explicit(self) -> None:
        required = {
            "Korean": (
                self.korean,
                (
                    "공개 저장소의 권한 있는 owner 또는 maintainer만",
                    "제3자 저장소 추천 채널이 아닙니다",
                    "공개 코드만 검토",
                    "license, contribution rules, AI policy",
                    "unpublished review-only first-pass patch",
                    "선택 사항",
                    "공개 PR 전에는 대상 저장소의 권한 있는 owner 또는 maintainer가 별도로 확인",
                    "외부 저장소의 권한 있는 maintainer가 별도로 검토·승인",
                    "30분은 초기 scoping/session 범위",
                    "답변·patch·완료 시간 약속이 아닙니다",
                ),
            ),
            "English": (
                self.english,
                (
                    "Only an authorized owner or maintainer of the target public repository should post",
                    "not a third-party repository nomination channel",
                    "public code only",
                    "license, contribution rules, and AI policy",
                    "optional unpublished, review-only first-pass patch",
                    "Separate confirmation from an authorized owner or maintainer of the target repository is required before any public PR",
                    "Any baseline must be separately reviewed and approved by an authorized maintainer of the target external repository",
                    "`30 minutes` covers only the initial scoping/session",
                    "not a response, patch, or completion-time guarantee",
                ),
            ),
        }
        for name, (text, fragments) in required.items():
            with self.subTest(readme=name):
                first_screen = text[: text.index("[Apache ShardingSphere-JDBC]")]
                for fragment in fragments:
                    self.assertIn(fragment, first_screen)

    def test_assisted_pilot_has_no_unsafe_private_or_turnaround_inverse(self) -> None:
        combined = "\n".join((self.korean, self.english, self.guide)).lower()
        for unsafe in (
            "send credentials privately",
            "share credentials privately",
            "privately send credentials",
            "provide private repository access",
            "grant me private access",
            "private first-pass patch",
            "30-minute turnaround",
            "30-minute fit check",
            "i will prepare a private first-pass patch",
            "requires a person to approve",
            "a person reviews the minimized candidate",
            "a human-approved exact baseline",
            "assisted help or a private first-pass patch is allowed",
            "30분 내 답변",
            "30분 내 패치",
            "30분 fit check",
            "맞으면 대표 operation 하나의 private first-pass patch를 준비합니다",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertNotIn(unsafe.lower(), combined)

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
            "Throughout this guide, human approval means separate approval by an authorized owner or maintainer of the external repository",
            compact_section,
        )
        self.assertIn(
            "An external-user result exists only when an external team or developer applies the RouteContract dependency, an exact baseline approved by an authorized owner or maintainer of that external repository, and the candidate check to a representative operation in their own repository, and that check succeeds in the repository's upstream public CI",
            compact_section,
        )
        self.assertIn(
            "Assisted help or an unpublished review-only first-pass patch is allowed only when the target repository's license, contribution rules, and AI policy permit it; a RouteContract-maintainer-only, same-checkout, local-only, or draft result is insufficient",
            compact_section,
        )
        self.assertIn(
            "does not establish adoption, endorsement, production use, performance, or security",
            compact_section,
        )
        self.assertNotIn("owner-run", compact_section)
        self.assertNotIn("A person reviews", compact_section)

        detailed = self.guide[
            self.guide.index("## 4. Review and approve the first baseline") :
            self.guide.index("## 5. Run the candidate check in CI")
        ]
        detailed_compact = " ".join(detailed.split())
        for required in (
            "authorized owner or maintainer of the target external repository",
            "those exact reviewed candidate bytes",
            "normal review process",
            "RouteContract maintainer, an assistant, a tool, or CI cannot substitute",
        ):
            self.assertIn(required, detailed_compact)


if __name__ == "__main__":
    unittest.main()
