#!/usr/bin/env python3
"""Fast structural acceptance tests for the isolated Maven pilot contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PARENT_POM = REPOSITORY_ROOT / "examples" / "maven-pilot" / "pom.xml"
INTEGRATION_POM = (
    REPOSITORY_ROOT / "examples" / "maven-pilot" / "integration-tests" / "pom.xml"
)
BUSINESS_TEST = (
    REPOSITORY_ROOT
    / "examples"
    / "maven-pilot"
    / "integration-tests"
    / "src"
    / "test"
    / "java"
    / "io"
    / "github"
    / "ym0506"
    / "routecontract"
    / "examples"
    / "maven"
    / "MavenBusinessMySqlTest.java"
)
PILOT_TEST = (
    REPOSITORY_ROOT
    / "examples"
    / "maven-pilot"
    / "integration-tests"
    / "src"
    / "routeContractPilot"
    / "java"
    / "io"
    / "github"
    / "ym0506"
    / "routecontract"
    / "examples"
    / "maven"
    / "MavenRouteContractPilotTest.java"
)
APPROVED_BASELINE = (
    REPOSITORY_ROOT
    / "examples"
    / "maven-pilot"
    / "integration-tests"
    / "src"
    / "routeContractPilot"
    / "resources"
    / "route-contracts"
    / "orders.find-by-user-id.json"
)
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify-maven-pilot.sh"
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-release-assets.py"
CHECKSUM_PREPARER = REPOSITORY_ROOT / "scripts" / "prepare_maven_v0_1_0_checksums.py"
INTEGRATION_GUIDE = REPOSITORY_ROOT / "docs" / "first-integration.md"
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
MAVEN_NAMESPACE = {"m": "http://maven.apache.org/POM/4.0.0"}
ROUTECONTRACT_GROUP = "io.github.ym0506.routecontract"
ROUTECONTRACT_ARTIFACT = "routecontract-shardingsphere-5.5"
REPOSITORY_ID = "routecontract-verified-file-repository"
VALID_GRAPH = """\
[INFO] --- dependency:3.11.0:tree (default-cli) @ consumer ---
[INFO] example:consumer:jar:1.0.0
[INFO] +- org.apache.shardingsphere:shardingsphere-jdbc:jar:5.5.3:test
[INFO] +- org.apache.calcite:calcite-core:jar:1.42.0:test
[INFO] |  +- net.minidev:json-smart:jar:2.4.10:test
[INFO] |     \\- net.minidev:accessors-smart:jar:2.4.9:test
[INFO] +- org.apache.calcite:calcite-linq4j:jar:1.42.0:test
[INFO] +- com.fasterxml.jackson.core:jackson-databind:jar:2.18.9:test
[INFO] \\- io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:jar:0.1.0:test
"""


def parse_pom(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def required_text(element: ET.Element, path: str) -> str:
    child = element.find(path, MAVEN_NAMESPACE)
    if child is None or child.text is None:
        raise AssertionError(f"missing Maven element: {path}")
    return child.text.strip()


def direct_dependencies(project: ET.Element) -> list[ET.Element]:
    return project.findall("m:dependencies/m:dependency", MAVEN_NAMESPACE)


def coordinate(dependency: ET.Element) -> tuple[str, str]:
    return (
        required_text(dependency, "m:groupId"),
        required_text(dependency, "m:artifactId"),
    )


def dependency_by_coordinate(
    dependencies: list[ET.Element], group_id: str, artifact_id: str
) -> ET.Element:
    matches = [
        dependency
        for dependency in dependencies
        if coordinate(dependency) == (group_id, artifact_id)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one dependency {group_id}:{artifact_id}, found {len(matches)}"
        )
    return matches[0]


def exclusions(dependency: ET.Element) -> set[tuple[str, str]]:
    return {
        (
            required_text(exclusion, "m:groupId"),
            required_text(exclusion, "m:artifactId"),
        )
        for exclusion in dependency.findall(
            "m:exclusions/m:exclusion", MAVEN_NAMESPACE
        )
    }


class MavenPilotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parent = parse_pom(PARENT_POM)
        cls.integration = parse_pom(INTEGRATION_POM)
        cls.verifier = VERIFIER.read_text(encoding="utf-8")
        cls.guide = INTEGRATION_GUIDE.read_text(encoding="utf-8")
        cls.ci_workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        cls.business_test = BUSINESS_TEST.read_text(encoding="utf-8")
        cls.pilot_test = PILOT_TEST.read_text(encoding="utf-8")

    def _run_graph_parser(self, graph: str) -> subprocess.CompletedProcess[str]:
        marker = 'python3 -I - "$graph_log" <<\'PY\'\n'
        start = self.verifier.index(marker) + len(marker)
        parser = self.verifier[start : self.verifier.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            graph_path = Path(temporary) / "dependency-tree.log"
            graph_path.write_text(graph, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-I", "-c", parser, graph_path],
                capture_output=True,
                check=False,
                text=True,
            )

    def _run_surefire_parser(
        self, outcome: str, report: str
    ) -> subprocess.CompletedProcess[str]:
        marker = '        "$expected_candidate_path" "$expected_approved_path" <<\'PY\'\n'
        start = self.verifier.index(marker) + len(marker)
        parser = self.verifier[start : self.verifier.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            report_directory = Path(temporary) / "reports"
            report_directory.mkdir()
            (report_directory / "TEST-pilot.xml").write_text(report, encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    parser,
                    outcome,
                    report_directory,
                    "/tmp/candidate.json",
                    "/tmp/approved.json",
                ],
                capture_output=True,
                check=False,
                text=True,
            )

    def test_profile_off_has_no_routecontract_resolution_or_pilot_source(self) -> None:
        self.assertIsNone(self.integration.find("m:repositories", MAVEN_NAMESPACE))
        self.assertNotIn(
            (ROUTECONTRACT_GROUP, ROUTECONTRACT_ARTIFACT),
            {coordinate(dependency) for dependency in direct_dependencies(self.integration)},
        )

        default_plugins = self.integration.findall(
            "m:build/m:plugins/m:plugin", MAVEN_NAMESPACE
        )
        self.assertNotIn(
            "build-helper-maven-plugin",
            {required_text(plugin, "m:artifactId") for plugin in default_plugins},
        )
        self.assertEqual(
            [],
            self.integration.findall(
                "m:build/m:plugins/m:plugin/m:executions/m:execution/"
                "m:configuration/m:sources/m:source",
                MAVEN_NAMESPACE,
            ),
        )
        self.assertFalse(
            APPROVED_BASELINE.exists() or APPROVED_BASELINE.is_symlink(),
            "the source fixture must not ship any approved or synthetic baseline",
        )

        for required_assertion in (
            "assertThrows(ClassNotFoundException.class",
            "RouteContract provider must be absent when the profile is off",
            "the profile-off build must not create a RouteContract candidate",
            "routecontractDependency=ABSENT",
        ):
            self.assertIn(required_assertion, self.business_test)
        self.assertNotIn(
            "the fixture must not ship a synthetic or approved baseline",
            self.business_test,
        )
        self.assertIn(
            "source fixture must not contain an approved or synthetic baseline",
            self.verifier,
        )
        for effective_model_assertion in (
            "org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom",
            "profile-off effective POM activated pilot-only dependency management",
            "profile-off effective POM activated pilot-only dependency",
            "profile-off effective POM inherited pilot-only exclusions",
            "profile-off effective POM activated the RouteContract repository",
            "profile-off effective POM activated the pilot source root",
        ):
            self.assertIn(effective_model_assertion, self.verifier)

    def test_opt_in_profile_is_the_only_resolution_and_source_boundary(self) -> None:
        profiles = self.integration.findall("m:profiles/m:profile", MAVEN_NAMESPACE)
        self.assertEqual(1, len(profiles))
        profile = profiles[0]
        self.assertEqual("routecontract-pilot", required_text(profile, "m:id"))
        self.assertEqual(
            "routecontractPilot",
            required_text(profile, "m:activation/m:property/m:name"),
        )
        self.assertEqual(
            "true", required_text(profile, "m:activation/m:property/m:value")
        )
        self.assertIsNone(profile.find("m:activation/m:activeByDefault", MAVEN_NAMESPACE))

        repositories = profile.findall("m:repositories/m:repository", MAVEN_NAMESPACE)
        self.assertEqual(1, len(repositories))
        repository = repositories[0]
        self.assertEqual(REPOSITORY_ID, required_text(repository, "m:id"))
        self.assertEqual(
            "${routecontractRepositoryUrl}", required_text(repository, "m:url")
        )
        self.assertEqual(
            "fail", required_text(repository, "m:releases/m:checksumPolicy")
        )
        self.assertEqual("never", required_text(repository, "m:releases/m:updatePolicy"))
        self.assertEqual("false", required_text(repository, "m:snapshots/m:enabled"))

        profile_dependencies = direct_dependencies(profile)
        routecontract = dependency_by_coordinate(
            profile_dependencies, ROUTECONTRACT_GROUP, ROUTECONTRACT_ARTIFACT
        )
        self.assertEqual("0.1.0", required_text(routecontract, "m:version"))
        self.assertEqual("test", required_text(routecontract, "m:scope"))
        all_routecontract_dependencies = [
            dependency
            for dependency in self.integration.findall(".//m:dependency", MAVEN_NAMESPACE)
            if coordinate(dependency) == (ROUTECONTRACT_GROUP, ROUTECONTRACT_ARTIFACT)
        ]
        self.assertEqual([routecontract], all_routecontract_dependencies)

        added_sources = profile.findall(
            "m:build/m:plugins/m:plugin/m:executions/m:execution/"
            "m:configuration/m:sources/m:source",
            MAVEN_NAMESPACE,
        )
        self.assertEqual(
            ["src/routeContractPilot/java"],
            [(source.text or "").strip() for source in added_sources],
        )
        self.assertEqual(
            "target/routecontract",
            required_text(
                profile,
                "m:build/m:plugins/m:plugin[m:artifactId='maven-surefire-plugin']/"
                "m:configuration/m:systemPropertyVariables/m:routecontract.candidateRoot",
            ),
        )
        self.assertEqual(
            "${routecontract.artifactJarPath}",
            required_text(
                profile,
                "m:build/m:plugins/m:plugin[m:artifactId='maven-surefire-plugin']/"
                "m:configuration/m:systemPropertyVariables/m:routecontract.artifactJarPath",
            ),
        )
        includes = profile.findall(
            "m:build/m:plugins/m:plugin/m:configuration/m:includes/m:include",
            MAVEN_NAMESPACE,
        )
        self.assertEqual([], includes)
        for configuration in profile.findall(
            "m:build/m:plugins/m:plugin/m:configuration", MAVEN_NAMESPACE
        ):
            self.assertNotEqual("override", configuration.get("combine.self"))

    def test_dependency_versions_and_fail_closed_exclusions_are_exact(self) -> None:
        properties = self.parent.find("m:properties", MAVEN_NAMESPACE)
        self.assertIsNotNone(properties)
        assert properties is not None
        values = {
            child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
            for child in properties
        }
        self.assertEqual("5.5.3", values["shardingsphere.version"])
        self.assertEqual("1.42.0", values["calcite.version"])
        self.assertEqual("26.7.0", values["mysql.connector.version"])
        self.assertEqual("1.21.4", values["testcontainers.version"])

        parent_managed = self.parent.findall(
            "m:dependencyManagement/m:dependencies/m:dependency", MAVEN_NAMESPACE
        )
        profile_only_management = {
            ("com.fasterxml.jackson", "jackson-bom"),
            ("org.apache.calcite", "calcite-core"),
            ("org.apache.calcite", "calcite-linq4j"),
            ("net.minidev", "json-smart"),
            ("net.minidev", "accessors-smart"),
        }
        self.assertTrue(
            profile_only_management.isdisjoint(
                {coordinate(dependency) for dependency in parent_managed}
            )
        )

        base_dependencies = direct_dependencies(self.integration)
        self.assertEqual(
            set(),
            exclusions(
                dependency_by_coordinate(
                    base_dependencies,
                    "org.apache.shardingsphere",
                    "shardingsphere-jdbc",
                )
            ),
        )
        self.assertEqual(
            set(),
            exclusions(
                dependency_by_coordinate(
                    base_dependencies, "com.mysql", "mysql-connector-j"
                )
            ),
        )
        self.assertNotIn(
            ("org.apache.calcite", "calcite-core"),
            {coordinate(dependency) for dependency in base_dependencies},
        )

        profile = self.integration.find("m:profiles/m:profile", MAVEN_NAMESPACE)
        self.assertIsNotNone(profile)
        assert profile is not None
        profile_managed = profile.findall(
            "m:dependencyManagement/m:dependencies/m:dependency", MAVEN_NAMESPACE
        )
        self.assertEqual(
            profile_only_management,
            {coordinate(dependency) for dependency in profile_managed},
        )
        jackson_bom = dependency_by_coordinate(
            profile_managed, "com.fasterxml.jackson", "jackson-bom"
        )
        self.assertEqual("${jackson2.version}", required_text(jackson_bom, "m:version"))
        self.assertEqual("pom", required_text(jackson_bom, "m:type"))
        self.assertEqual("import", required_text(jackson_bom, "m:scope"))

        dependencies = direct_dependencies(profile)
        self.assertEqual(
            {
                ("org.locationtech.jts.io", "jts-io-common"),
                ("com.google.protobuf", "protobuf-java"),
            },
            exclusions(
                dependency_by_coordinate(
                    dependencies,
                    "org.apache.shardingsphere",
                    "shardingsphere-jdbc",
                )
            ),
        )
        self.assertEqual(
            {
                ("org.locationtech.jts.io", "jts-io-common"),
                ("com.google.protobuf", "protobuf-java"),
            },
            exclusions(
                dependency_by_coordinate(
                    dependencies, "org.apache.calcite", "calcite-core"
                )
            ),
        )
        self.assertEqual(
            {("com.google.protobuf", "protobuf-java")},
            exclusions(
                dependency_by_coordinate(
                    dependencies, "com.mysql", "mysql-connector-j"
                )
            ),
        )

        for exact_graph_assertion in (
            'versions != {"5.5.3"}',
            "expected exactly one {qualifier}unclassified test-scope JAR dependency",
            '"prefix": prefix',
            '"depth": depth',
            'coordinate["type"] == "jar"',
            'coordinate["classifier"] is None',
            'coordinate["scope"] == "test"',
            'coordinate["depth"] == 1',
            "expected exactly one dependency-tree plugin section and one project root",
            "FasterXML Jackson dependencies must be unclassified JARs in an allowed scope",
            '("org.apache.calcite", "calcite-core", "1.42.0")',
            '("org.apache.calcite", "calcite-linq4j", "1.42.0")',
            '("net.minidev", "json-smart", "2.4.10")',
            '("net.minidev", "accessors-smart", "2.4.9")',
            'jackson_versions != {"2.18.9"}',
            '("org.locationtech.jts.io", "jts-io-common")',
            '("com.google.protobuf", "protobuf-java")',
        ):
            self.assertIn(exact_graph_assertion, self.verifier)

    def test_same_checkout_graph_parser_enforces_structural_coordinates(self) -> None:
        completed = self._run_graph_parser(VALID_GRAPH)
        self.assertEqual(0, completed.returncode, completed.stderr)

        mutations = {
            "pom type": VALID_GRAPH.replace(
                "shardingsphere-jdbc:jar:5.5.3:test",
                "shardingsphere-jdbc:pom:5.5.3:test",
            ),
            "classifier": VALID_GRAPH.replace(
                "routecontract-shardingsphere-5.5:jar:0.1.0:test",
                "routecontract-shardingsphere-5.5:jar:tests:0.1.0:test",
            ),
            "wrong scope": VALID_GRAPH.replace(
                "shardingsphere-jdbc:jar:5.5.3:test",
                "shardingsphere-jdbc:jar:5.5.3:compile",
            ),
            "transitive depth": VALID_GRAPH.replace(
                "[INFO] \\- io.github.ym0506.routecontract",
                "[INFO] |  \\- io.github.ym0506.routecontract",
            ),
            "Jackson provided scope": VALID_GRAPH.replace(
                "jackson-databind:jar:2.18.9:test",
                "jackson-databind:jar:2.18.9:provided",
            ),
            "Jackson classifier": VALID_GRAPH.replace(
                "jackson-databind:jar:2.18.9:test",
                "jackson-databind:jar:tests:2.18.9:test",
            ),
            "Jackson pom type": VALID_GRAPH.replace(
                "jackson-databind:jar:2.18.9:test",
                "jackson-databind:pom:2.18.9:test",
            ),
            "Jackson namespace prefix collision": VALID_GRAPH.replace(
                "com.fasterxml.jackson.core:jackson-databind",
                "com.fasterxml.jacksonevil:fake",
            ),
            "second project root": VALID_GRAPH.replace(
                "[INFO] \\- io.github.ym0506.routecontract",
                "[INFO] example:second:jar:1.0.0\n"
                "[INFO] \\- io.github.ym0506.routecontract",
            ),
            "second plugin section": VALID_GRAPH + VALID_GRAPH,
            "unprefixed dependency": VALID_GRAPH.replace(
                "[INFO] |  +- net.minidev:json-smart",
                "[INFO] net.minidev:json-smart",
            ),
        }
        for name, graph in mutations.items():
            with self.subTest(name=name):
                completed = self._run_graph_parser(graph)
                self.assertNotEqual(0, completed.returncode)

    def test_surefire_parser_rejects_unrelated_selected_testcase(self) -> None:
        expected_class = (
            "io.github.ym0506.routecontract.examples.maven."
            "MavenRouteContractPilotTest"
        )
        passing = (
            '<testsuite tests="1" failures="0" errors="0" skipped="0">'
            f'<testcase classname="{expected_class}" '
            'name="keepsTheApprovedExecutionStructure"/>'
            "</testsuite>"
        )
        completed = self._run_surefire_parser("matched", passing)
        self.assertEqual(0, completed.returncode, completed.stderr)
        unrelated = (
            '<testsuite tests="1" failures="0" errors="0" skipped="0">'
            '<testcase classname="x.Unrelated" name="other"/>'
            "</testsuite>"
        )
        completed = self._run_surefire_parser("matched", unrelated)
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("exact selected Maven pilot testcase", completed.stderr)

    def test_verifier_requires_sha256_and_rejects_bad_sidecar_before_pilot(self) -> None:
        checksum_definition = (
            'checksum_algorithm_property="-Daether.checksums.algorithms.'
            '${repository_id}=SHA-256"'
        )
        self.assertIn(checksum_definition, self.verifier)
        installer_sha256 = hashlib.sha256(INSTALLER.read_bytes()).hexdigest()
        installer_hash_assignments = [
            line
            for line in self.verifier.splitlines()
            if line.startswith("expected_installer_sha256=")
        ]
        self.assertEqual(
            [f'expected_installer_sha256="{installer_sha256}"'],
            installer_hash_assignments,
        )
        self.assertIn(
            '|| die "release installer does not match the reviewed hash"',
            self.verifier,
        )
        self.assertNotIn(
            "release installer does not match the immutable v0.1.0 hash",
            self.verifier,
        )
        helper_sha256 = hashlib.sha256(CHECKSUM_PREPARER.read_bytes()).hexdigest()
        self.assertIn(
            f'expected_checksum_preparer_sha256="{helper_sha256}"', self.verifier
        )
        self.assertIn(
            f'expected_checksum_helper_sha256="{helper_sha256}"', self.guide
        )
        self.assertEqual(
            4,
            self.verifier.count("-DroutecontractPilot=true"),
            "every opt-in resolver/build path must stay explicit",
        )
        self.assertEqual(
            4,
            self.verifier.count('"$checksum_algorithm_property"'),
            "every opt-in Maven invocation must require repository-scoped SHA-256",
        )
        selector = (
            "-Dtest=io.github.ym0506.routecontract.examples.maven."
            "MavenRouteContractPilotTest#keepsTheApprovedExecutionStructure"
        )
        self.assertEqual(4, self.verifier.count(selector))
        self.assertEqual(
            4,
            self.verifier.count("-Droutecontract.artifactJarPath="),
            "every opt-in Maven invocation must bind the runtime to its exact cached JAR",
        )
        self.assertNotIn("-DskipTests dependency:tree", self.verifier)

        mutation = self.verifier.index('path.write_bytes(("0" * 64 + "\\n")')
        negative_run = self.verifier.index(
            selector,
            mutation,
        )
        exit_one = self.verifier.index(
            'test "$bad_checksum_exit" = 1', negative_run
        )
        candidate_absent = self.verifier.index(
            "bad-checksum run executed the pilot and created a candidate", exit_one
        )
        marker_absent = self.verifier.index(
            "bad-checksum run reached the RouteContract pilot", candidate_absent
        )
        first_pilot_run = self.verifier.index(
            'missing_log="$temporary_root/missing-baseline.log"', marker_absent
        )
        self.assertLess(mutation, negative_run)
        self.assertLess(negative_run, exit_one)
        self.assertLess(exit_one, candidate_absent)
        self.assertLess(candidate_absent, marker_absent)
        self.assertLess(marker_absent, first_pilot_run)
        self.assertIn(
            "Checksum validation failed, expected '",
            self.verifier[negative_run:first_pilot_run],
        )
        self.assertNotIn("-DskipTests clean test", self.verifier[mutation:first_pilot_run])

        for validation in (
            "routecontract.candidateRoot must be set by the isolated pilot profile",
            "routecontract.candidateRoot must be relative to the owning module",
            "routecontract.candidateRoot must stay below the owning module",
            "routecontract.artifactJarPath must identify the exact cached Release JAR",
            "routecontract.artifactJarPath must be an absolute non-symlink path",
            "RouteContract must be loaded from the exact cached Release JAR",
            "the SPI provider class must be loaded from the exact cached Release JAR",
            "matchingServiceDescriptorJars()",
            "JarURLConnection jarConnection = (JarURLConnection) connection;",
            "Path.of(jarConnection.getJarFileURL().toURI()).toRealPath()",
        ):
            self.assertIn(validation, self.pilot_test)

        for fixture in (
            "bad_checksum_fixture",
            "graph_fixture",
            "missing_fixture",
            "matched_fixture",
        ):
            self.assertIn(
                "seed_profile_off_cache \\\n"
                f'    "${fixture}"',
                self.verifier,
            )
        self.assertIn(
            'graph_cache_coordinate="$temporary_root/cache-graph/',
            self.verifier,
        )
        self.assertIn(
            "for cache in cache-missing-baseline cache-mechanical-match",
            self.verifier,
        )

    def test_ci_pins_maven_install_and_uploads_pilot_summary(self) -> None:
        install_start = self.ci_workflow.index(
            "      - name: Install exact Apache Maven 3.9.14"
        )
        install_end = self.ci_workflow.index(
            "      - name: Install checksum-locked report-package test dependencies",
            install_start,
        )
        install = self.ci_workflow[install_start:install_end]
        for required in (
            "timeout-minutes: 10",
            'maven_url="https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.14/apache-maven-3.9.14-bin.tar.gz"',
            'expected_sha512="d50af8ab5e6005b46a07f0ce9d3719e67cfdf898da988a84871304cd59fb1af0fef2f99dea709e6e66f21f732f905979b5c2dce6b6860406f60a70e84d9cf0b8"',
            "Apache Maven 3.9.14 (996c630dbc656c76214ce58821dcc58be960875b)",
            'printf \'MAVEN_HOME=%s\\n\' "${maven_home}" >> "${GITHUB_ENV}"',
            'printf \'%s\\n\' "${maven_home}/bin" >> "${GITHUB_PATH}"',
        ):
            self.assertIn(required, install)
        self.assertLess(install.index("sha512sum --check --strict"), install.index("tar --extract"))

        pilot_start = self.ci_workflow.index(
            "      - name: Verify isolated Maven 3.9.14 onboarding pilot"
        )
        pilot_end = self.ci_workflow.index(
            "      - name: Record runner environment", pilot_start
        )
        pilot = self.ci_workflow[pilot_start:pilot_end]
        for required in (
            "timeout-minutes: 20",
            'summary="build/ci-evidence/maven-pilot-summary.txt"',
            './scripts/verify-maven-pilot.sh > "${partial}"',
            'mv "${partial}" "${summary}"',
        ):
            self.assertIn(required, pilot)

        upload_start = self.ci_workflow.index(
            "      - name: Upload test and environment evidence"
        )
        upload_end = self.ci_workflow.index("\n  dependency-review:", upload_start)
        upload = self.ci_workflow[upload_start:upload_end]
        self.assertIn("build/ci-evidence/maven-pilot-summary.txt", upload)

    def test_missing_baseline_and_synthetic_match_remain_non_adoption_evidence(self) -> None:
        write_candidate = self.pilot_test.index("store.writeCandidate(")
        missing_failure = self.pilot_test.index(
            'fail("No approved baseline. Review "', write_candidate
        )
        self.assertIn(
            '+ " and copy it to " + approvedPath + " only after human approval.");',
            self.pilot_test[missing_failure:],
        )
        manifest_match = self.pilot_test.index(
            "ManifestAssertions.assertMatched(", missing_failure
        )
        self.assertLess(write_candidate, missing_failure)
        self.assertLess(missing_failure, manifest_match)

        missing_run = self.verifier.index(
            'missing_log="$temporary_root/missing-baseline.log"'
        )
        missing_exit = self.verifier.index(
            'test "$missing_exit" = 1', missing_run
        )
        baseline_absent = self.verifier.index(
            "missing-baseline harness unexpectedly contains an approved baseline",
            missing_exit,
        )
        synthetic_copy = self.verifier.index(
            'cp "$candidate" "$matched_approved"', baseline_absent
        )
        matched_run = self.verifier.index(
            'matched_log="$temporary_root/mechanical-match.log"', synthetic_copy
        )
        source_unchanged = self.verifier.index(
            "verifier wrote a baseline into the source fixture", matched_run
        )
        self.assertLess(missing_run, missing_exit)
        self.assertLess(missing_exit, baseline_absent)
        self.assertLess(baseline_absent, synthetic_copy)
        self.assertLess(synthetic_copy, matched_run)
        self.assertLess(matched_run, source_unchanged)
        self.assertIn(
            "copy proves a mechanical match path, not human approval or external adoption",
            self.verifier,
        )

        summary_start = self.verifier.index(
            "'ROUTECONTRACT_MAVEN_FIXTURE profileOff=PASS"
        )
        summary = self.verifier[summary_start:]
        self.assertIn(
            "ROUTECONTRACT_MAVEN_FIXTURE "
            "evidenceBoundary=SAME_CHECKOUT_NOT_EXTERNAL_ADOPTION "
            "humanApprovedBaseline=false",
            summary,
        )
        for unsafe_detail in (
            "$temporary_root",
            "$provided_assets",
            "$release_assets_directory",
            "$repository_uri",
            "$candidate",
            "$matched_candidate",
        ):
            self.assertNotIn(
                unsafe_detail,
                summary,
                f"final evidence summary must not expose run-local detail {unsafe_detail}",
            )


if __name__ == "__main__":
    unittest.main()
