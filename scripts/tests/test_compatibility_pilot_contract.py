#!/usr/bin/env python3
"""Contract tests for the sealed Quarkiverse compatibility pilot packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PILOT = (
    REPOSITORY_ROOT
    / "docs"
    / "compatibility-pilots"
    / "quarkiverse-quarkus-shardingsphere-jdbc"
)
README = PILOT / "README.md"
PATCH = PILOT / "routecontract-pilot.patch"
REPRODUCER = PILOT / "reproduce.sh"
MAVEN_SETTINGS = PILOT / "maven-settings.xml"
EXPECTED_CANDIDATE = PILOT / "expected-candidate.sha256"
RECEIPT = PILOT / "receipt.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompatibilityPilotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README.read_text(encoding="utf-8")
        cls.reproducer = REPRODUCER.read_text(encoding="utf-8")
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_packet_files_are_regular_and_receipt_hashes_current_bytes(self) -> None:
        for path in (
            README,
            PATCH,
            REPRODUCER,
            MAVEN_SETTINGS,
            EXPECTED_CANDIDATE,
            RECEIPT,
        ):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)

        patch_record = self.receipt["patch"]
        self.assertEqual(PATCH.stat().st_size, patch_record["bytes"])
        self.assertEqual(sha256(PATCH), patch_record["sha256"])
        reproducer_record = self.receipt["reproducer"]
        self.assertEqual(REPRODUCER.stat().st_size, reproducer_record["bytes"])
        self.assertEqual(sha256(REPRODUCER), reproducer_record["sha256"])
        self.assertIn(reproducer_record["sha256"], self.readme)
        self.assertEqual(
            sha256(EXPECTED_CANDIDATE),
            reproducer_record["expectedCandidateFileSha256"],
        )
        settings_record = reproducer_record["mavenSettings"]
        self.assertEqual(MAVEN_SETTINGS.name, settings_record["file"])
        self.assertEqual(MAVEN_SETTINGS.stat().st_size, settings_record["bytes"])
        self.assertEqual(sha256(MAVEN_SETTINGS), settings_record["sha256"])
        self.assertIn(settings_record["sha256"], self.readme)
        settings_root = ET.fromstring(MAVEN_SETTINGS.read_bytes())
        self.assertTrue(settings_root.tag.endswith("}settings"))
        self.assertEqual([], list(settings_root))
        self.assertEqual(0, settings_record["documentChildCount"])

    def test_patch_scope_is_exact_and_contains_no_baseline(self) -> None:
        changed_paths = [
            line.removeprefix("+++ b/")
            for line in self.patch.splitlines()
            if line.startswith("+++ b/")
        ]
        self.assertEqual(self.receipt["patch"]["changedPaths"], changed_paths)
        self.assertEqual(2, len(changed_paths))
        self.assertFalse(
            any(
                path.endswith("resources/route-contracts/accounts.insert.json")
                for path in changed_paths
            )
        )
        self.assertFalse(self.receipt["patch"]["approvedBaselineIncluded"])

    def test_reproducer_is_syntax_valid_and_seed_cleanup_is_symlink_safe(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(REPRODUCER)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

        source_guard = self.reproducer.index(
            'find "$SEED_DIR" -type l -print -quit'
        )
        copy = self.reproducer.index('cp -R "$SEED_DIR"/. "$MAVEN_LOCAL_REPO"/')
        copied_guard = self.reproducer.index(
            'find "$MAVEN_LOCAL_REPO" -type l -print -quit', copy
        )
        coordinate_removal = self.reproducer.index(
            'rm -rf -- "$MAVEN_LOCAL_REPO/io/github/ym0506/routecontract"',
            copied_guard,
        )
        self.assertLess(source_guard, copy)
        self.assertLess(copy, copied_guard)
        self.assertLess(copied_guard, coordinate_removal)

    def test_java_and_maven_runtime_are_fail_closed_and_isolated(self) -> None:
        for source_contract in (
            '[[ "$JAVA_HOME" == /* ]]',
            '[[ "${JAVA_HOME%/}" == "$JAVA_HOME_CANONICAL" ]]',
            'readonly JAVA_EXECUTABLE="$JAVA_HOME_CANONICAL/bin/java"',
            'java_isolated -XshowSettings:properties -version',
            '[[ "$JAVA_SPECIFICATION_VERSION" == "17" ]]',
            '[[ "$MAVEN_VERSION" == "$EXPECTED_MAVEN_VERSION" ]]',
            '[[ "$MAVEN_JAVA_VERSION" == "17" || "$MAVEN_JAVA_VERSION" == 17.* ]]',
            '[[ "$MAVEN_RUNTIME_CANONICAL" == "$JAVA_HOME_CANONICAL" ]]',
            '$(cd "$SCRATCH_DIR" && mvn_isolated --version)',
            '--settings "$MAVEN_SETTINGS"',
            '--global-settings "$MAVEN_SETTINGS"',
        ):
            self.assertIn(source_contract, self.reproducer)

        java_wrapper_start = self.reproducer.index("java_isolated() {")
        java_wrapper_end = self.reproducer.index("\n}\n", java_wrapper_start)
        java_wrapper = self.reproducer[java_wrapper_start:java_wrapper_end]
        java_probe = self.reproducer.index(
            "java_isolated -XshowSettings:properties -version"
        )
        self.assertLess(java_wrapper_end, java_probe)
        for environment_variable in (
            "BASH_ENV",
            "ENV",
            "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "_JAVA_OPTIONS",
        ):
            self.assertIn(f"-u {environment_variable}", java_wrapper)

        wrapper_start = self.reproducer.index("mvn_isolated() {")
        wrapper_end = self.reproducer.index("\n}\n", wrapper_start)
        wrapper = self.reproducer[wrapper_start:wrapper_end]
        for environment_variable in (
            "BASH_ENV",
            "ENV",
            "MAVEN_ARGS",
            "MAVEN_BASEDIR",
            "MAVEN_OPTS",
            "MAVEN_DEBUG_OPTS",
            "MAVEN_CONFIG",
            "MAVEN_PROJECTBASEDIR",
            "MAVEN_USER_HOME",
            "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "_JAVA_OPTIONS",
        ):
            self.assertIn(f"-u {environment_variable}", wrapper)
        self.assertIn("MAVEN_SKIP_RC=true", wrapper)
        self.assertEqual(
            set(self.receipt["reproducer"]["runtimeContract"][
                "nestedProcessEnvironmentCleared"
            ]),
            {
                "BASH_ENV",
                "ENV",
                "MAVEN_ARGS",
                "MAVEN_BASEDIR",
                "MAVEN_OPTS",
                "MAVEN_DEBUG_OPTS",
                "MAVEN_CONFIG",
                "MAVEN_PROJECTBASEDIR",
                "MAVEN_USER_HOME",
                "JAVA_TOOL_OPTIONS",
                "JDK_JAVA_OPTIONS",
                "_JAVA_OPTIONS",
            },
        )

        # The executable invocation belongs only to the isolated wrapper; all
        # version/build calls must use that wrapper.
        self.assertEqual(1, self.reproducer.count("    mvn \\\n"))
        self.assertEqual(4, self.reproducer.count("mvn_isolated "))

    def test_consumer_cache_artifact_and_origin_are_read_back(self) -> None:
        cache_verifier = self.reproducer[
            self.reproducer.index("verify_consumer_cache() {") :
        ]
        for contract in (
            'require_hash "$cached_jar" "$EXPECTED_JAR_SHA256"',
            'require_hash "$cached_pom" "$EXPECTED_POM_SHA256"',
            "require_digest_sidecar",
            '"$cached_jar_sidecar" "$EXPECTED_JAR_SHA256"',
            '"$cached_pom_sidecar" "$EXPECTED_POM_SHA256"',
            '"$RELEASE_JAR>routecontract-v0.1.0-local="',
            '"$CACHED_RELEASE_POM>routecontract-v0.1.0-local="',
            'consumer-cache _remote.repositories binding changed',
        ):
            self.assertIn(contract, cache_verifier)
        self.assertIn(
            'data not in (expected, expected + b"\\n")',
            self.reproducer,
        )

        provenance = self.receipt["reproducer"][
            "consumerCacheVerificationContract"
        ]
        self.assertEqual(
            self.receipt["routeContract"]["jarSha256"],
            provenance["jarSha256"],
        )
        self.assertEqual(
            self.receipt["routeContract"]["pomSha256"],
            provenance["pomSha256"],
        )
        self.assertTrue(provenance["exactSha256SidecarsRequired"])
        self.assertEqual(
            "64 lowercase hex bytes with optional final LF",
            provenance["sha256SidecarEncoding"],
        )
        self.assertEqual(
            "routecontract-v0.1.0-local",
            provenance["exactRemoteRepositoryBinding"],
        )
        verified = self.receipt["verification"]["artifactResolution"]
        for key in (
            "consumerCacheJarHashVerified",
            "consumerCachePomHashVerified",
            "sha256SidecarsVerified",
            "callerProvidedMavenArgsIgnored",
            "callerProvidedMavenBaseDirIgnored",
            "callerProvidedMavenConfigIgnored",
            "callerProvidedMavenDebugOptsIgnored",
            "callerProvidedMavenOptsIgnored",
            "callerProvidedMavenProjectBaseDirIgnored",
            "callerProvidedMavenUserHomeIgnored",
            "callerProvidedJavaToolOptionsIgnored",
            "callerProvidedJdkJavaOptionsIgnored",
            "callerProvidedUnderscoreJavaOptionsIgnored",
        ):
            self.assertTrue(verified[key], key)
        self.assertEqual(
            "routecontract-v0.1.0-local",
            verified["remoteRepositoryBinding"],
        )

    def test_profile_off_and_profile_on_tests_cannot_be_skipped(self) -> None:
        for option in (
            "-DskipTests=false",
            "-Dmaven.test.skip=false",
            "-Dmaven.test.failure.ignore=false",
        ):
            self.assertEqual(2, self.reproducer.count(option))

        for identity in (
            "ShardingsphereJdbcTest.xml",
            "ShardingsphereJdbcTest'",
            "writeYourOwnUnitTest",
            "ShardingsphereJdbcDevModeTest.xml",
            "ShardingsphereJdbcDevModeTest'",
            "writeYourOwnDevModeTest",
            "ShardingTablesTest.xml",
            "ShardingTablesTest'",
            "expected three exact profile-off report triples",
            "profile-off Surefire report inventory is not the exact reviewed set",
            'expected_totals = {"tests": "1", "failures": "0", "errors": "0", "skipped": "0"}',
        ):
            self.assertIn(identity, self.reproducer)

    def test_receipt_keeps_claim_boundary_explicit(self) -> None:
        boundary = self.receipt["claimBoundary"]
        for key in (
            "completeRoutePlanClaimed",
            "mysqlVerified",
            "productionSupportClaimed",
            "externalMaintainerParticipated",
            "externalUserEvidence",
            "adoptionEvidence",
            "endorsementClaimed",
        ):
            self.assertIs(boundary[key], False, key)
        self.assertFalse(
            self.receipt["verification"]["profileOn"]["approvedBaselineCreated"]
        )
        normalized_readme = " ".join(
            self.readme.replace("**", "").replace("`", "").split()
        )
        for phrase in (
            "not MySQL evidence",
            "a user result, adoption, production support or endorsement",
            "No human-approved baseline is included or created",
            "does not seal a test-scope comparison or the exact discovery time",
            "this packet makes no HTTP-capture claim",
            "Each attempt begins with SQLExecutionHook.start",
            "does not satisfy the project's strict definition of an actual external user integration",
        ):
            self.assertIn(phrase, normalized_readme)

        route_contract = self.receipt["routeContract"]
        self.assertFalse(route_contract["testScopeComparisonSealed"])
        self.assertFalse(route_contract["exactDiscoveryTimeSealed"])
        observed = self.receipt["verification"]["observedOperation"]
        self.assertEqual("SQLExecutionHook.start", observed["attemptStartCallback"])
        self.assertIn("finishSuccess", observed["callbackReturnedMeaning"])
        self.assertFalse(observed["terminalSignalsAreBusinessOutcomes"])

        combined_claims = "\n".join((self.readme, self.patch, json.dumps(self.receipt)))
        for unsupported in (
            "test scope did not expose",
            "separate runtime class loader before the JUnit test",
            "visible during application boot",
            "reported attempt corresponds to the ShardingSphere hook report made after",
        ):
            self.assertNotIn(unsupported, combined_claims)

    def test_packet_does_not_embed_private_paths_or_secrets(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                README,
                PATCH,
                REPRODUCER,
                MAVEN_SETTINGS,
                EXPECTED_CANDIDATE,
                RECEIPT,
            )
        )
        for forbidden in (
            "/Users/",
            "/private/tmp/",
            "atat9828@naver.com",
            "ghp_",
            "github_pat_",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
