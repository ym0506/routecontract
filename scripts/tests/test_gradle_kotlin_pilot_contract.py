#!/usr/bin/env python3
"""Fast structural tests for the verified Gradle Kotlin DSL pilot lane."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY_ROOT / "examples" / "gradle-kotlin-pilot"
BUILD = FIXTURE / "build.gradle.kts"
README = FIXTURE / "README.md"
PILOT_TEST = (
    FIXTURE
    / "src"
    / "routeContractPilot"
    / "java"
    / "io"
    / "github"
    / "ym0506"
    / "routecontract"
    / "examples"
    / "gradle"
    / "kotlin"
    / "GradleKotlinRouteContractPilotTest.java"
)
BUSINESS_TEST = (
    FIXTURE
    / "src"
    / "test"
    / "java"
    / "io"
    / "github"
    / "ym0506"
    / "routecontract"
    / "examples"
    / "gradle"
    / "kotlin"
    / "GradleKotlinBusinessMySqlTest.java"
)
MYSQL_FIXTURE = BUSINESS_TEST.with_name("MySqlShardingFixture.java")
ORDER_QUERY = BUSINESS_TEST.with_name("OrderQueryService.java")
APPROVED_BASELINE = (
    FIXTURE
    / "src"
    / "routeContractPilot"
    / "resources"
    / "route-contracts"
    / "orders.find-by-user-id.json"
)
GUIDE = REPOSITORY_ROOT / "docs" / "first-integration.md"
CI = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify-gradle-kotlin-pilot.sh"
PROVENANCE_VALIDATOR = (
    REPOSITORY_ROOT / "scripts" / "validate-gradle-kotlin-pilot-provenance.py"
)


class GradleKotlinPilotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.guide = GUIDE.read_text(encoding="utf-8")
        cls.ci = CI.read_text(encoding="utf-8")
        cls.verifier = VERIFIER.read_text(encoding="utf-8")
        cls.pilot_test = PILOT_TEST.read_text(encoding="utf-8")
        cls.business_test = BUSINESS_TEST.read_text(encoding="utf-8")
        cls.mysql_fixture = MYSQL_FIXTURE.read_text(encoding="utf-8")
        cls.order_query = ORDER_QUERY.read_text(encoding="utf-8")

    def test_fixture_files_are_regular_and_source_has_no_baseline(self) -> None:
        for path in (
            BUILD,
            README,
            PILOT_TEST,
            BUSINESS_TEST,
            MYSQL_FIXTURE,
            ORDER_QUERY,
            VERIFIER,
            PROVENANCE_VALIDATOR,
            CI,
        ):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
        self.assertFalse(APPROVED_BASELINE.exists() or APPROVED_BASELINE.is_symlink())

    def test_marker_bounded_kotlin_lane_is_documented_as_the_tested_source(self) -> None:
        start_marker = "// ROUTECONTRACT_KOTLIN_DSL_START"
        end_marker = "// ROUTECONTRACT_KOTLIN_DSL_END"
        self.assertEqual(1, self.build.count(start_marker))
        self.assertEqual(1, self.build.count(end_marker))
        start = self.build.index(start_marker)
        end = self.build.index(end_marker, start)
        lane = self.build[start:end]
        for required in (
            'providers.gradleProperty("routecontractPilot")',
            'providers.gradleProperty("routecontractRepository")',
            'providers.environmentVariable("ROUTECONTRACT_REPOSITORY")',
            'sourceSets.create("routeContractPilot")',
            'RouteContract repository must be an absolute local filesystem directory',
            'RouteContract repository path must not contain symbolic-link components',
            'routecontract-shardingsphere-5.5-0.1.2.jar',
            'routecontract-shardingsphere-5.5-0.1.2.pom',
            'expectedRouteContractPomSha256',
            'RouteContract repository POM SHA-256 mismatch:',
            'exclusiveContent',
            'name = "routeContractPilotRepository"',
            'url = uri(routeContractRepositoryRoot.toUri())',
            'metadataSources',
            'mavenPom()',
            'includeModule(',
            'add(pilot.implementationConfigurationName, expectedRouteContractCoordinate)',
            'routeContractArtifact.file.toPath().toRealPath()',
            'enforcedPlatform("com.fasterxml.jackson:jackson-bom:2.18.9")',
            '"com.mysql:mysql-connector-j:26.7.0"',
            '"org.testcontainers:junit-jupiter:1.21.4"',
            '"org.testcontainers:mysql:1.21.4"',
            '"org.junit.jupiter:junit-jupiter:5.14.3"',
            '"org.junit.platform:junit-platform-launcher:1.14.3"',
            '"org.apache.calcite:calcite-core"',
            'version { strictly("1.42.0") }',
            '"net.minidev:json-smart"',
            'version { strictly("2.4.10") }',
            '"net.minidev:accessors-smart"',
            'version { strictly("2.4.9") }',
            '"io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2"',
            'tasks.register("routeContractPilotGraph")',
            'tasks.register(\n        "routeContractPilotArtifactProvenance"',
            'isTransitive = false',
            'ResolvedDependencyResult',
            'ModuleComponentSelector',
            'ModuleComponentIdentifier',
            'tasks.register<org.gradle.api.tasks.testing.Test>("routeContractPilot")',
            'JMessageDigest.getInstance("SHA-256")',
            'JFiles.deleteIfExists(path)',
            'dependsOn(routeContractPilotPrepare, routeContractPilotGraph)',
            'println("ROUTECONTRACT_GRADLE_GRAPH VERIFIED")',
        ):
            self.assertIn(required, lane)
        for forbidden in (
            "mavenLocal()",
            "publishToMavenLocal",
            "project(\"",
            "files(routeContractRepositoryJar.toFile())",
            "java.nio.",
            "java.security.",
            "java.util.",
        ):
            self.assertNotIn(forbidden, lane)

        self.assertIn("### Gradle Kotlin DSL opt-in lane", self.guide)
        self.assertIn("../examples/gradle-kotlin-pilot/README.md", self.guide)
        self.assertIn(start_marker.removeprefix("// "), self.guide)
        self.assertIn(end_marker.removeprefix("// "), self.guide)
        self.assertIn("H2 `MODE=MySQL`", self.guide)
        self.assertIn("does not satisfy the published MySQL 8.4.11 boundary", self.guide)
        self.assertIn("ROUTECONTRACT_GRADLE_GRAPH VERIFIED", self.guide)
        self.assertIn("exclusive local-Maven-repository isolation", self.guide)
        self.assertIn(
            "wrong, missing-metadata, POM-tampered, and JAR-tampered",
            " ".join(self.guide.split()),
        )
        self.assertIn("preinstalled JDK 17", self.guide)
        self.assertIn(
            "not evidence that a different Java-21-only target",
            " ".join(self.guide.split()),
        )
        self.assertNotIn("Gradle 9.5.1", self.guide)
        self.assertNotIn(
            "needs Kotlin DSL, stop and report that fit blocker",
            self.guide,
        )

        for prelude_line in (
            "import java.nio.file.Files as JFiles",
            "import java.nio.file.LinkOption as JLinkOption",
            "import java.nio.file.Path as JPath",
            "import java.security.MessageDigest as JMessageDigest",
            "import java.util.HexFormat as JHexFormat",
            "plugins { java }",
            "repositories { mavenCentral() }",
        ):
            self.assertIn(prelude_line, self.build)
            self.assertIn(prelude_line, self.readme)
            self.assertIn(prelude_line, self.guide)
            self.assertIn(prelude_line, self.verifier)

    def test_profile_off_and_real_mysql_pilot_boundaries_are_explicit(self) -> None:
        lane_start = self.build.index("// ROUTECONTRACT_KOTLIN_DSL_START")
        coordinate = (
            '"io.github.ym0506.routecontract:'
            'routecontract-shardingsphere-5.5:0.1.2"'
        )
        self.assertEqual(1, self.build.count(coordinate))
        self.assertGreater(self.build.index(coordinate), lane_start)
        for assertion in (
            "assertThrows(ClassNotFoundException.class",
            "RouteContract provider must be absent from the profile-off graph",
            "the profile-off build must not create a RouteContract candidate",
            "routecontractDependency=ABSENT",
        ):
            self.assertIn(assertion, self.business_test)

        for assertion in (
            "mysql:8.4.11@sha256:",
            "PreparedStatement",
            'statement.setLong(1, userId)',
            "SELECT COUNT(*) FROM t_order WHERE user_id = ?",
        ):
            self.assertIn(
                assertion,
                self.mysql_fixture + self.order_query + self.pilot_test,
            )
        for assertion in (
            "RouteContract.captureResult(",
            ".hasExactlyObservedPhysicalAttempts(1)",
            '.observesExactlyDataSourceNames("ds_0")',
            "store.writeCandidate(approvedPath, candidatePath, candidate)",
            "only after human approval",
            "candidateCheck=MATCHED",
        ):
            self.assertIn(assertion, self.pilot_test)

    def test_verifier_is_syntax_valid_and_checks_all_five_outcomes(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(VERIFIER)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        for required in (
            "source fixture must not contain an approved or synthetic baseline",
            "marker-only fixture must start without a project .gradle directory",
            "markerCopy=PASS",
            "repositoryBoundary=PASS",
            "gavResolution=PASS",
            "gavNoRemoteFallback=DECOY_REJECTED_OFFLINE_FRESH_CACHE",
            "gavNegativeCases=PASS",
            "environmentIsolation=ALLOWLISTED",
            "cacheIsolation=PASS",
            "artifactOrigin=EXACT_COORDINATE_JAR",
            "assert_no_fixed_line()",
            "relative RouteContract repository must exit exactly 1",
            "symlink-backed RouteContract repository must exit exactly 1",
            "enabled pilot without a RouteContract repository must exit exactly 1",
            "nonexistent RouteContract repository must exit exactly 1",
            "wrong RouteContract GAV must exit exactly 1",
            "missing RouteContract GAV metadata must exit exactly 1",
            "tampered RouteContract GAV POM must exit exactly 1",
            "RouteContract repository POM SHA-256 mismatch:",
            "tampered RouteContract GAV must exit exactly 1",
            "RouteContract runtime JAR SHA-256 mismatch:",
            "profile-off run created a pilot candidate",
            "ROUTECONTRACT_GRADLE_GRAPH VERIFIED",
            "missing-baseline pilot must exit exactly 1",
            "approved baseline must be absent immediately before synthetic copy",
            "exclusive_regular_copy",
            "os.O_EXCL",
            'hasattr(os, "O_NOFOLLOW")',
            "synthetic baseline copy changed candidate bytes",
            "ROUTECONTRACT_GRADLE_KOTLIN_PILOT candidateCheck=MATCHED",
            "matched run changed the synthetic baseline lstat identity",
            "verifier mutated the source fixture baseline",
            '&& test ! -L "$fixture_source/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"',
            "verifier created a project-local .gradle cache",
            "--exclude .gradle --exclude build",
            "prepare_case_caches()",
            "run_gradle_case()",
            '"GRADLE_USER_HOME=$case_gradle_home"',
            '--project-cache-dir "$case_project_cache"',
            "--no-configuration-cache",
            "--no-watch-fs",
            'env -i "${case_environment[@]}"',
            '"HOME=$case_home"',
            '"TMPDIR=$case_tmp"',
            '"LC_ALL=C"',
            'routeContractDecoyRepository',
            'routecontract.decoyRepository',
            '"-Droutecontract.decoyRepository=$repository"',
            '"-Droutecontract.decoyRepository=$tampered_gav_repository"',
            "exclusive lookup did not name the designated missing POM",
            "exclusive lookup fell through to the valid ordinary decoy repository",
            "routeContractPilotArtifactProvenance",
            "--offline",
            "Gradle user cache must start absent",
            "Gradle project cache must start absent",
            "verifier did not use exactly fourteen independent Gradle cache pairs",
            "verifier reused a Gradle user/project cache pair",
            "jarSha256=%s pomSha256=%s candidateSha256=%s",
            "provenanceSha256=%s",
            "candidateSha256=%s",
            "wrapperDistributionSha256=f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d",
            "wrapperJarSha256=7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172",
            "runtimeOriginEvidence=HASHED_EPHEMERAL_OBSERVATIONS",
            "rev-parse --show-toplevel",
            '[[ "$git_toplevel" == "$repository_root" ]]',
            'source_binding="unbound-source-copy"',
        ):
            self.assertIn(required, self.verifier)
        for case_name in (
            "missing-repository-property",
            "relative-repository",
            "nonexistent-repository",
            "symlink-repository",
            "wrong-gav",
            "missing-gav",
            "tampered-pom",
            "tampered-gav",
            "marker-copy",
            "profile-off",
            "gav-origin",
            "graph",
            "missing-baseline",
            "matched",
        ):
            self.assertEqual(
                1,
                self.verifier.count(f"prepare_case_caches {case_name}"),
                case_name,
            )
        self.assertIn("parse_junit_report missing", self.verifier)
        self.assertIn("parse_junit_report matched", self.verifier)
        final_cache_gate = self.verifier.index(
            '|| die "verifier reused a Gradle user/project cache pair"'
        )
        preserved_receipt_copy = self.verifier.index(
            '"$receipt" "$provenance_output" "$(dirname -- "$provenance_output")"'
        )
        final_success_marker = self.verifier.index(
            "ROUTECONTRACT_GRADLE_KOTLIN_VERIFY markerCopy=PASS"
        )
        self.assertLess(final_cache_gate, preserved_receipt_copy)
        self.assertLess(preserved_receipt_copy, final_success_marker)

    def test_required_ci_workflow_runs_and_preserves_the_full_lane(self) -> None:
        for required in (
            "gradle-kotlin-pilot:\n"
            "    name: Gradle Kotlin DSL / MySQL assisted pilot",
            "expected_index_sha256=\"7849adf417f0170b08d01902b023e8b328d8796f7c2aeacc471eb7acf8e2b217\"",
            "./scripts/verify-gradle-kotlin-pilot.sh",
            "--release-assets-dir \"${ROUTECONTRACT_RELEASE_ASSETS}\"",
            "--provenance-output \"${provenance}\"",
            "python3 -I scripts/validate-gradle-kotlin-pilot-provenance.py",
            "routecontract-gradle-kotlin-evidence-${{ github.sha }}",
            "verifier-evidence.sha256",
        ):
            self.assertIn(required, self.ci)

    def test_provenance_output_contract_executes_and_rejects_origin_drift(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "gradle_kotlin_provenance", PROVENANCE_VALIDATOR
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            coordinate = (
                root
                / "io"
                / "github"
                / "ym0506"
                / "routecontract"
                / "routecontract-shardingsphere-5.5"
                / "0.1.2"
            )
            coordinate.mkdir(parents=True)
            jar = coordinate / "routecontract-shardingsphere-5.5-0.1.2.jar"
            pom = coordinate / "routecontract-shardingsphere-5.5-0.1.2.pom"
            jar.write_bytes(b"synthetic provenance contract jar\n")
            pom.write_bytes(b"synthetic provenance contract pom\n")
            jar_sha = hashlib.sha256(jar.read_bytes()).hexdigest()
            pom_sha = hashlib.sha256(pom.read_bytes()).hexdigest()
            module.JAR_SHA256 = jar_sha
            module.POM_SHA256 = pom_sha
            provenance = root / "provenance.json"
            document = {
                "schemaVersion": 1,
                "coordinate": module.COORDINATE,
                "resolvedComponent": module.COORDINATE,
                "pathsEphemeral": True,
                "repositoryRoot": str(root),
                "jar": {"path": str(jar), "sha256": jar_sha},
                "pom": {"path": str(pom), "sha256": pom_sha},
                "origins": {
                    "routeContractClass": str(jar),
                    "providerClass": str(jar),
                    "serviceDescriptorCount": 1,
                    "serviceDescriptorJars": [str(jar)],
                },
                "claimBoundary": {
                    "dependencyVerification": (
                        "selected-invariant-graph-and-pre-operation-runtime-origin"
                    ),
                    "externalUser": False,
                    "humanApprovedBaseline": False,
                    "adoption": False,
                },
            }
            provenance.write_text(
                json.dumps(document, sort_keys=True) + "\n", encoding="utf-8"
            )
            validated = module.validate(provenance)
            self.assertEqual(module.COORDINATE, validated["resolvedComponent"])
            valid_runtime_observation = copy.deepcopy(document)
            document["origins"]["providerClass"] = str(pom)
            provenance.write_text(json.dumps(document) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                module.ProvenanceError, "API and provider origins"
            ):
                module.validate(provenance)

            for dotted_key, wrong_value in (
                ("schemaVersion", True),
                ("pathsEphemeral", 1),
                ("origins.serviceDescriptorCount", True),
                ("claimBoundary.externalUser", 0),
            ):
                drifted = copy.deepcopy(valid_runtime_observation)
                cursor = drifted
                components = dotted_key.split(".")
                for component in components[:-1]:
                    cursor = cursor[component]
                cursor[components[-1]] = wrong_value
                provenance.write_text(json.dumps(drifted) + "\n", encoding="utf-8")
                with self.subTest(runtime_dotted_key=dotted_key):
                    with self.assertRaises(module.ProvenanceError):
                        module.validate(provenance)

            receipt = {
                "schemaVersion": 2,
                "coordinate": module.COORDINATE,
                "source": {
                    "revision": None,
                    "tree": None,
                    "clean": False,
                    "binding": "unbound-source-copy",
                },
                "toolchain": {
                    "gradleVersion": "8.14.4",
                    "javaMajor": 17,
                    "wrapperDistributionUrl": module.WRAPPER_DISTRIBUTION_URL,
                    "wrapperDistributionSha256": (
                        module.WRAPPER_DISTRIBUTION_SHA256
                    ),
                    "wrapperJarSha256": module.WRAPPER_JAR_SHA256,
                },
                "artifacts": {
                    "jar": {
                        "fileName": "routecontract-shardingsphere-5.5-0.1.2.jar",
                        "sha256": jar_sha,
                        "retained": False,
                    },
                    "pom": {
                        "fileName": "routecontract-shardingsphere-5.5-0.1.2.pom",
                        "sha256": pom_sha,
                        "retained": False,
                    },
                },
                "verification": {
                    "environmentIsolation": "env-i-allowlist",
                    "caseCount": 14,
                    "cachePairsUnique": True,
                    "decoyFallback": "designated-exclusive-repository-only",
                    "runtimePreflight": (
                        "before-mysql-and-routecontract-operation"
                    ),
                    "pathsEphemeral": True,
                    "missingBaseline": {
                        "outcome": "EXPECTED_MISSING_HUMAN_BASELINE",
                        "candidateSha256": "b" * 64,
                        "candidateBytes": 1,
                        "junitSha256": "c" * 64,
                        "junitBytes": 2,
                        "tests": 1,
                        "failures": 1,
                        "errors": 0,
                        "skipped": 0,
                        "runtimeObservationSha256": "d" * 64,
                    },
                    "matched": {
                        "outcome": "SYNTHETIC_MATCH_PASS",
                        "candidateSha256": "b" * 64,
                        "candidateBytes": 1,
                        "junitSha256": "e" * 64,
                        "junitBytes": 2,
                        "tests": 1,
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                        "runtimeObservationSha256": "f" * 64,
                    },
                },
                "claimBoundary": {
                    "externalUser": False,
                    "humanApprovedBaseline": False,
                    "adoption": False,
                    "endorsement": False,
                },
            }
            provenance.write_text(
                json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
            )
            validated_receipt = module.validate(provenance)
            self.assertEqual(2, validated_receipt["schemaVersion"])
            clean_receipt = copy.deepcopy(receipt)
            clean_receipt["source"] = {
                "revision": "1" * 40,
                "tree": "2" * 40,
                "clean": True,
                "binding": "exact-clean-checkout",
            }
            provenance.write_text(
                json.dumps(clean_receipt, sort_keys=True) + "\n", encoding="utf-8"
            )
            self.assertTrue(module.validate(provenance)["source"]["clean"])
            mixed_object_format = copy.deepcopy(clean_receipt)
            mixed_object_format["source"]["tree"] = "2" * 64
            provenance.write_text(
                json.dumps(mixed_object_format) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(module.ProvenanceError, "object formats"):
                module.validate(provenance)

            type_drift_cases = (
                ("schemaVersion", 2.0),
                ("toolchain.javaMajor", 17.0),
                ("verification.caseCount", 14.0),
                ("artifacts.jar.retained", 0),
                ("claimBoundary.externalUser", 0),
                ("verification.matched.candidateBytes", True),
                ("toolchain.wrapperJarSha256", "a" * 64),
            )
            for dotted_key, wrong_value in type_drift_cases:
                drifted = copy.deepcopy(receipt)
                cursor = drifted
                components = dotted_key.split(".")
                for component in components[:-1]:
                    cursor = cursor[component]
                cursor[components[-1]] = wrong_value
                provenance.write_text(json.dumps(drifted) + "\n", encoding="utf-8")
                with self.subTest(dotted_key=dotted_key):
                    with self.assertRaises(module.ProvenanceError):
                        module.validate(provenance)

            duplicate_root = json.dumps(receipt)[:-1] + ', "schemaVersion": 2}'
            provenance.write_text(duplicate_root + "\n", encoding="utf-8")
            with self.assertRaisesRegex(module.ProvenanceError, "duplicate JSON key"):
                module.validate(provenance)

            receipt["verification"]["matched"]["candidateSha256"] = "0" * 64
            provenance.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                module.ProvenanceError, "candidates must be byte-identical"
            ):
                module.validate(provenance)

        completed = subprocess.run(
            ["python3", "-I", str(PROVENANCE_VALIDATOR), str(BUILD)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertTrue(
            completed.stdout.startswith("ROUTECONTRACT_GRADLE_PROVENANCE_ERROR "),
            completed.stdout,
        )


if __name__ == "__main__":
    unittest.main()
