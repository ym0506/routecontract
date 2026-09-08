#!/usr/bin/env python3
"""Acceptance for lossless OSV release-branch metadata and unconditional rejection."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "verify-supply-chain-policy.py"
SPEC = importlib.util.spec_from_file_location("osv_fixed_branches_checker", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

# Minimized exact records from the pinned Maven OSV database; prose, version
# enumeration, and unrelated scanner metadata are omitted, never range events.
# See docs/osv-fixed-branches-acceptance.md for provenance and field boundaries.
PINNED_ENTRIES = json.loads(r'''
[
  {
    "package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-java", "version": "3.21.9"},
    "groups": [{"ids": ["GHSA-735f-pc8j-v9w8"]}],
    "vulnerabilities": [
      {
        "id": "GHSA-735f-pc8j-v9w8",
        "database_specific": {"severity": "HIGH"},
        "affected": [
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-java", "purl": "pkg:maven/com.google.protobuf/protobuf-java"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.25.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-javalite", "purl": "pkg:maven/com.google.protobuf/protobuf-javalite"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.25.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-kotlin", "purl": "pkg:maven/com.google.protobuf/protobuf-kotlin"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.25.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-kotlin-lite", "purl": "pkg:maven/com.google.protobuf/protobuf-kotlin-lite"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.25.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "RubyGems", "name": "google-protobuf", "purl": "pkg:gem/google-protobuf"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "3.25.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "RubyGems", "name": "google-protobuf", "purl": "pkg:gem/google-protobuf"}, "ranges": [{"events": [{"introduced": "4.0.0.rc.1"}, {"fixed": "4.27.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "RubyGems", "name": "google-protobuf", "purl": "pkg:gem/google-protobuf"}, "ranges": [{"events": [{"introduced": "4.28.0.rc.1"}, {"fixed": "4.28.2"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-kotlin-lite", "purl": "pkg:maven/com.google.protobuf/protobuf-kotlin-lite"}, "ranges": [{"events": [{"introduced": "4.0.0-RC1"}, {"fixed": "4.27.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-kotlin-lite", "purl": "pkg:maven/com.google.protobuf/protobuf-kotlin-lite"}, "ranges": [{"events": [{"introduced": "4.28.0-RC1"}, {"fixed": "4.28.2"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-kotlin", "purl": "pkg:maven/com.google.protobuf/protobuf-kotlin"}, "ranges": [{"events": [{"introduced": "4.0.0-RC1"}, {"fixed": "4.27.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-kotlin", "purl": "pkg:maven/com.google.protobuf/protobuf-kotlin"}, "ranges": [{"events": [{"introduced": "4.28.0-RC1"}, {"fixed": "4.28.2"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-javalite", "purl": "pkg:maven/com.google.protobuf/protobuf-javalite"}, "ranges": [{"events": [{"introduced": "4.0.0-RC1"}, {"fixed": "4.27.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-javalite", "purl": "pkg:maven/com.google.protobuf/protobuf-javalite"}, "ranges": [{"events": [{"introduced": "4.28.0-RC1"}, {"fixed": "4.28.2"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-java", "purl": "pkg:maven/com.google.protobuf/protobuf-java"}, "ranges": [{"events": [{"introduced": "4.0.0-RC1"}, {"fixed": "4.27.5"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "com.google.protobuf:protobuf-java", "purl": "pkg:maven/com.google.protobuf/protobuf-java"}, "ranges": [{"events": [{"introduced": "4.28.0-RC1"}, {"fixed": "4.28.2"}], "type": "ECOSYSTEM"}]}
        ]
      }
    ]
  },
  {
    "package": {"ecosystem": "Maven", "name": "commons-lang:commons-lang", "version": "2.4"},
    "groups": [{"ids": ["GHSA-j288-q9x7-2f5v"]}],
    "vulnerabilities": [
      {
        "id": "GHSA-j288-q9x7-2f5v",
        "database_specific": {"severity": "MODERATE"},
        "affected": [
          {"package": {"ecosystem": "Maven", "name": "org.apache.commons:commons-lang3", "purl": "pkg:maven/org.apache.commons/commons-lang3"}, "ranges": [{"events": [{"introduced": "3.0"}, {"fixed": "3.18.0"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "commons-lang:commons-lang", "purl": "pkg:maven/commons-lang/commons-lang"}, "ranges": [{"events": [{"introduced": "2.0"}, {"last_affected": "2.6"}], "type": "ECOSYSTEM"}]}
        ]
      }
    ]
  },
  {
    "package": {"ecosystem": "Maven", "name": "net.minidev:json-smart", "version": "2.5.0"},
    "groups": [{"ids": ["GHSA-pq2g-wx69-c263"]}],
    "vulnerabilities": [
      {
        "id": "GHSA-pq2g-wx69-c263",
        "database_specific": {"severity": "HIGH"},
        "affected": [
          {"package": {"ecosystem": "Maven", "name": "net.minidev:json-smart", "purl": "pkg:maven/net.minidev/json-smart"}, "ranges": [{"events": [{"introduced": "2.5.0"}, {"fixed": "2.5.2"}], "type": "ECOSYSTEM"}]}
        ]
      }
    ]
  },
  {
    "package": {"ecosystem": "Maven", "name": "org.apache.calcite:calcite-core", "version": "1.38.0"},
    "groups": [{"ids": ["GHSA-c2rv-hwqm-wjpg"]}],
    "vulnerabilities": [
      {
        "id": "GHSA-c2rv-hwqm-wjpg",
        "database_specific": {"severity": "MODERATE"},
        "affected": [
          {"package": {"ecosystem": "Maven", "name": "org.apache.calcite:calcite-core", "purl": "pkg:maven/org.apache.calcite/calcite-core"}, "ranges": [{"events": [{"introduced": "1.5.0"}, {"fixed": "1.42.0"}], "type": "ECOSYSTEM"}]}
        ]
      }
    ]
  },
  {
    "package": {"ecosystem": "Maven", "name": "org.apache.commons:commons-lang3", "version": "3.15.0"},
    "groups": [{"ids": ["GHSA-j288-q9x7-2f5v"]}],
    "vulnerabilities": [
      {
        "id": "GHSA-j288-q9x7-2f5v",
        "database_specific": {"severity": "MODERATE"},
        "affected": [
          {"package": {"ecosystem": "Maven", "name": "org.apache.commons:commons-lang3", "purl": "pkg:maven/org.apache.commons/commons-lang3"}, "ranges": [{"events": [{"introduced": "3.0"}, {"fixed": "3.18.0"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "commons-lang:commons-lang", "purl": "pkg:maven/commons-lang/commons-lang"}, "ranges": [{"events": [{"introduced": "2.0"}, {"last_affected": "2.6"}], "type": "ECOSYSTEM"}]}
        ]
      }
    ]
  },
  {
    "package": {"ecosystem": "Maven", "name": "org.apache.httpcomponents.core5:httpcore5", "version": "5.2.3"},
    "groups": [{"ids": ["GHSA-hf6x-8p5f-cgmf"]}],
    "vulnerabilities": [
      {
        "id": "GHSA-hf6x-8p5f-cgmf",
        "database_specific": {"severity": "HIGH"},
        "affected": [
          {"package": {"ecosystem": "Maven", "name": "org.apache.httpcomponents.core5:httpcore5", "purl": "pkg:maven/org.apache.httpcomponents.core5/httpcore5"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "5.4.3"}], "type": "ECOSYSTEM"}]},
          {"package": {"ecosystem": "Maven", "name": "org.apache.httpcomponents.core5:httpcore5", "purl": "pkg:maven/org.apache.httpcomponents.core5/httpcore5"}, "ranges": [{"events": [{"introduced": "5.5-alpha1"}, {"fixed": "5.5-beta2"}], "type": "ECOSYSTEM"}]}
        ]
      }
    ]
  }
]
''')


def inventory(entries: list[dict]) -> dict:
    return {checker._scanner_purl(entry): {} for entry in entries}


def vulnerability(name: str = "com.example:library", *, ecosystem: str = "Maven",
                  ranges: object = None) -> dict:
    return {"affected": [{"package": {"name": name, "ecosystem": ecosystem},
                           "ranges": [] if ranges is None else ranges}]}


def release_range(version: object, kind: str = "ECOSYSTEM") -> dict:
    return {"type": kind, "events": [{"introduced": "0"}, {"fixed": version}]}


class OsvFixedBranchesTest(unittest.TestCase):
    def fixed(self, value: dict, name: str = "com.example:library") -> list[str]:
        return checker._fixed_versions(value, name)

    def test_pinned_protobuf_preserves_all_three_release_branches(self) -> None:
        entry = PINNED_ENTRIES[0]
        findings = checker._findings([entry], inventory([entry]))
        self.assertEqual(["3.25.5", "4.27.5", "4.28.2"], findings[0]["fixedVersions"])
        self.assertNotIn("fixedVersion", findings[0])

    def test_pinned_httpcore_preserves_stable_and_prerelease_branches(self) -> None:
        entry = PINNED_ENTRIES[-1]
        findings = checker._findings([entry], inventory([entry]))
        self.assertEqual(["5.4.3", "5.5-beta2"], findings[0]["fixedVersions"])

    def test_pinned_lang2_no_fix_is_still_a_finding(self) -> None:
        entry = PINNED_ENTRIES[1]
        findings = checker._findings([entry], inventory([entry]))
        self.assertEqual(1, len(findings))
        self.assertEqual([], findings[0]["fixedVersions"])
        with self.assertRaisesRegex(checker.PolicyError, "GHSA-j288-q9x7-2f5v"):
            checker._apply_vulnerability_policy(findings)

    def test_all_six_pinned_findings_remain_forbidden_and_reported(self) -> None:
        before = copy.deepcopy(PINNED_ENTRIES)
        findings = checker._findings(PINNED_ENTRIES, inventory(PINNED_ENTRIES))
        expected = {
            ("com.google.protobuf/protobuf-java@3.21.9", "GHSA-735f-pc8j-v9w8"): ["3.25.5", "4.27.5", "4.28.2"],
            ("commons-lang/commons-lang@2.4", "GHSA-j288-q9x7-2f5v"): [],
            ("net.minidev/json-smart@2.5.0", "GHSA-pq2g-wx69-c263"): ["2.5.2"],
            ("org.apache.calcite/calcite-core@1.38.0", "GHSA-c2rv-hwqm-wjpg"): ["1.42.0"],
            ("org.apache.commons/commons-lang3@3.15.0", "GHSA-j288-q9x7-2f5v"): ["3.18.0"],
            ("org.apache.httpcomponents.core5/httpcore5@5.2.3", "GHSA-hf6x-8p5f-cgmf"): ["5.4.3", "5.5-beta2"],
        }
        self.assertEqual({("pkg:maven/" + p, a): f for (p, a), f in expected.items()},
                         {(f["purl"], f["advisory"]): f["fixedVersions"] for f in findings})
        self.assertEqual(before, PINNED_ENTRIES)
        prefix = "vulnerability findings are forbidden by the pinned policy: "
        with self.assertRaises(checker.PolicyError) as caught:
            checker._apply_vulnerability_policy(list(reversed(findings)))
        self.assertTrue(str(caught.exception).startswith(prefix))
        self.assertEqual(findings, json.loads(str(caught.exception).removeprefix(prefix)))
        for finding in findings:
            with self.subTest(purl=finding["purl"]):
                with self.assertRaises(checker.PolicyError):
                    checker._apply_vulnerability_policy([finding])

    def test_successful_empty_findings_are_unchanged(self) -> None:
        self.assertEqual([], checker._apply_vulnerability_policy([]))
        entries = copy.deepcopy(PINNED_ENTRIES)
        for entry in entries:
            entry["vulnerabilities"] = []
            entry["groups"] = []
        self.assertEqual([], checker._findings(entries, inventory(entries)))

    def test_deduplicates_and_serializes_lexically_without_version_ranking(self) -> None:
        value = vulnerability(ranges=[release_range("2.9"), release_range("2.10", "SEMVER")])
        value["affected"].append(copy.deepcopy(value["affected"][0]))
        self.assertEqual(["2.10", "2.9"], self.fixed(value))

    def test_requires_exact_maven_ecosystem_and_package_name(self) -> None:
        for ecosystem, name in (("npm", "com.example:library"),
                                ("maven", "com.example:library"),
                                ("Maven", "com.example:other")):
            with self.subTest(ecosystem=ecosystem, name=name):
                with self.assertRaisesRegex(checker.PolicyError, "no affected record"):
                    self.fixed(vulnerability(name, ecosystem=ecosystem, ranges=[release_range("1.0")]))

    def test_other_ecosystem_same_name_does_not_add_a_release(self) -> None:
        value = vulnerability(ranges=[release_range("1.0")])
        value["affected"] += vulnerability(ecosystem="npm", ranges=[release_range("9.0")])["affected"]
        value["affected"] += vulnerability("com.example:other", ranges=[release_range("8.0")])["affected"]
        self.assertEqual(["1.0"], self.fixed(value))

    def test_git_commit_is_validated_but_never_a_release_version(self) -> None:
        git = release_range("a" * 40, "GIT")
        git["repo"] = "https://example.com/repository.git"
        value = vulnerability(ranges=[git, release_range("1.0", "SEMVER")])
        before = copy.deepcopy(value)
        self.assertEqual(["1.0"], self.fixed(value))
        self.assertEqual(before, value)
        self.assertEqual([], self.fixed(vulnerability(ranges=[git])))
        git["events"][-1]["fixed"] = 42
        with self.assertRaises(checker.PolicyError):
            self.fixed(vulnerability(ranges=[git]))

    def test_rejects_missing_unknown_or_malformed_range_type(self) -> None:
        for kind in (None, "", "UNKNOWN", 42, []):
            value = release_range("1.0")
            if kind is None:
                del value["type"]
            else:
                value["type"] = kind
            with self.subTest(kind=kind):
                with self.assertRaises(checker.PolicyError):
                    self.fixed(vulnerability(ranges=[value]))

    def test_rejects_malformed_affected_ranges_and_events(self) -> None:
        cases = [
            {}, {"affected": {}}, {"affected": [None]},
            vulnerability(ranges="wrong"), vulnerability(ranges=[None]),
            vulnerability(ranges=[{"type": "ECOSYSTEM", "events": "wrong"}]),
            vulnerability(ranges=[{"type": "ECOSYSTEM", "events": [None]}]),
        ]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(checker.PolicyError):
                    self.fixed(value)

    def test_rejects_empty_or_non_string_fixed_events_for_every_range_type(self) -> None:
        for kind in ("ECOSYSTEM", "SEMVER", "GIT"):
            for fixed in (None, "", " ", 42, [], {}):
                with self.subTest(kind=kind, fixed=fixed):
                    with self.assertRaises(checker.PolicyError):
                        self.fixed(vulnerability(ranges=[release_range(fixed, kind)]))

    def test_preserves_exact_inventory_and_group_identity_checks(self) -> None:
        entries = [copy.deepcopy(PINNED_ENTRIES[-1])]
        with self.assertRaisesRegex(checker.PolicyError, "package set does not exactly match"):
            checker._findings(entries, {})
        entries[0]["groups"][0]["ids"] = ["GHSA-unrelated"]
        with self.assertRaisesRegex(checker.PolicyError, "group/vulnerability ids differ"):
            checker._findings(entries, inventory(entries))


if __name__ == "__main__":
    unittest.main()
