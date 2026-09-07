#!/usr/bin/env python3
"""Check onboarding navigation and feedback-form integrity, not editorial wording."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ONBOARDING_PAGES = (
    "README.md",
    "README.en.md",
    "docs/start-here.md",
    "docs/user-feedback.md",
    "docs/first-integration.md",
    "docs/product-roadmap.md",
)
FEEDBACK_PATH = REPOSITORY_ROOT / ".github/ISSUE_TEMPLATE/stable-feedback.yml"


class OnboardingNavigationTest(unittest.TestCase):
    def test_local_markdown_navigation_targets_exist(self) -> None:
        for relative in ONBOARDING_PAGES:
            page = REPOSITORY_ROOT / relative
            # Ignore fenced examples: those contain illustrative paths, not navigation.
            text = re.sub(r"```.*?```", "", page.read_text(), flags=re.DOTALL)
            for destination in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text):
                parsed = urlsplit(destination)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(page=relative, link=destination):
                    target = (page.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(target.is_relative_to(REPOSITORY_ROOT))
                    self.assertTrue(target.exists(), f"Broken local link: {destination}")

    def test_public_feedback_links_resolve_to_checked_in_issue_forms(self) -> None:
        for relative in ONBOARDING_PAGES:
            text = (REPOSITORY_ROOT / relative).read_text()
            for template in re.findall(r"issues/new\?template=([A-Za-z0-9_.-]+)", text):
                with self.subTest(page=relative, template=template):
                    self.assertTrue((FEEDBACK_PATH.parent / template).is_file())

    def test_feedback_form_has_unique_field_ids_and_valid_control_structure(self) -> None:
        text = FEEDBACK_PATH.read_text()
        ids = re.findall(r"^    id: ([a-z][a-z0-9_]*)$", text, flags=re.MULTILINE)
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)), "Issue field IDs must be unique")
        controls = re.split(r"(?m)^  - type: ", text)[1:]
        self.assertTrue(controls)
        for control in controls:
            kind = control.splitlines()[0]
            self.assertIn(kind, {"markdown", "textarea", "input", "dropdown", "checkboxes"})
            self.assertIn("    attributes:\n", control)
            if kind == "markdown":
                self.assertIn("      value:", control)
                continue
            self.assertRegex(control, r"(?m)^    id: [a-z][a-z0-9_]*$")
            self.assertIn("      label:", control)
            if kind in {"dropdown", "checkboxes"}:
                self.assertIn("      options:\n", control)
                self.assertRegex(control, r"(?m)^        - \S")


if __name__ == "__main__":
    unittest.main()
