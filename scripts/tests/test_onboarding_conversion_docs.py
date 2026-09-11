#!/usr/bin/env python3
"""Check onboarding navigation and feedback-form integrity, not editorial wording."""

from pathlib import Path
from html.parser import HTMLParser
import re
import unittest
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ONBOARDING_PAGES = (
    "README.md",
    "README.ko.md",
    "README.en.md",
    "docs/reference-guide.md",
    "docs/reference-guide.ko.md",
    "docs/start-here.md",
    "docs/user-feedback.md",
    "docs/first-integration.md",
    "docs/first-project.md",
    "docs/first-project.ko.md",
    "docs/product-roadmap.md",
)
FEEDBACK_PATH = REPOSITORY_ROOT / ".github/ISSUE_TEMPLATE/stable-feedback.yml"


def navigation_text(page: Path) -> str:
    # Fenced examples contain illustrative paths, not navigation or real headings.
    return re.sub(r"```.*?```", "", page.read_text(), flags=re.DOTALL)


class HtmlNavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.destinations: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attribute = {"a": "href", "img": "src"}.get(tag)
        for key, value in attrs:
            if key == attribute and value:
                self.destinations.append(value)


def navigation_destinations(text: str) -> list[str]:
    parser = HtmlNavigationParser()
    parser.feed(text)
    return re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text) + parser.destinations


def markdown_anchors(text: str) -> set[str]:
    anchors = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', text))
    occurrences: dict[str, int] = {}
    for heading in re.findall(r"(?m)^#{1,6} +(.+?)(?: +#+)?$", text):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        occurrence = occurrences.get(slug, 0)
        occurrences[slug] = occurrence + 1
        anchors.add(f"{slug}-{occurrence}" if occurrence else slug)
    return anchors


class OnboardingNavigationTest(unittest.TestCase):
    def test_local_markdown_navigation_targets_exist(self) -> None:
        for relative in ONBOARDING_PAGES:
            page = REPOSITORY_ROOT / relative
            text = navigation_text(page)
            for destination in navigation_destinations(text):
                parsed = urlsplit(destination)
                if parsed.scheme or parsed.netloc:
                    continue
                with self.subTest(page=relative, link=destination):
                    target = (page.parent / unquote(parsed.path)).resolve() if parsed.path else page
                    self.assertTrue(target.is_relative_to(REPOSITORY_ROOT))
                    self.assertTrue(target.exists(), f"Broken local link: {destination}")
                    if parsed.fragment and target.suffix == ".md":
                        self.assertIn(
                            unquote(parsed.fragment), markdown_anchors(navigation_text(target)),
                            f"Broken local anchor: {destination}",
                        )

    def test_language_entry_pages_keep_detailed_guides_reachable(self) -> None:
        for relative, destinations in (
            ("README.md", {"README.ko.md", "docs/reference-guide.md"}),
            ("README.ko.md", {"README.md", "docs/reference-guide.ko.md"}),
            ("README.en.md", {"README.md"}),
        ):
            text = navigation_text(REPOSITORY_ROOT / relative)
            linked_paths = {
                unquote(urlsplit(destination).path)
                for destination in navigation_destinations(text)
            }
            with self.subTest(page=relative):
                self.assertTrue(destinations <= linked_paths, destinations - linked_paths)

    def test_published_readme_anchors_remain_available(self) -> None:
        for relative, required in (
            ("README.md", {"install-013", "quick-start"}),
            ("README.en.md", {
                "install-013", "quick-start", "approved-manifests-and-structural-manifest-diffs",
            }),
        ):
            with self.subTest(page=relative):
                anchors = markdown_anchors(navigation_text(REPOSITORY_ROOT / relative))
                self.assertTrue(required <= anchors, required - anchors)

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
