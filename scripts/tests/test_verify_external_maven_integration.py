from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-external-maven-integration.sh"
VALID_GRAPH = """\
[INFO] --- dependency:3.11.0:tree (default-cli) @ consumer ---
[INFO] example:consumer:jar:1.0.0
[INFO] +- org.apache.shardingsphere:shardingsphere-jdbc:jar:5.5.3:compile
[INFO] +- org.apache.calcite:calcite-core:jar:1.42.0:compile
[INFO] |  +- net.minidev:json-smart:jar:2.4.10:runtime
[INFO] |     \\- net.minidev:accessors-smart:jar:2.4.9:compile
[INFO] +- org.apache.calcite:calcite-linq4j:jar:1.42.0:test
[INFO] +- com.fasterxml.jackson.core:jackson-databind:jar:2.18.9:compile
[INFO] \\- io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:jar:0.1.0:test
"""


class ExternalMavenIntegrationVerifierTest(unittest.TestCase):
    def _run_graph_parser(self, graph: str) -> subprocess.CompletedProcess[str]:
        script = SCRIPT.read_text(encoding="utf-8")
        marker = 'python3 -I - "$graph_log" <<\'PY\'\n'
        start = script.index(marker) + len(marker)
        parser = script[start : script.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            graph_path = Path(temporary) / "dependency-tree.log"
            graph_path.write_text(graph, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-I", "-c", parser, graph_path],
                capture_output=True,
                check=False,
                text=True,
            )

    def _run_profile_parser(self, report: str) -> subprocess.CompletedProcess[str]:
        script = SCRIPT.read_text(encoding="utf-8")
        marker = '    "$ROUTECONTRACT_PROFILE_OFF_METHOD" <<\'PY\'\n'
        start = script.index(marker) + len(marker)
        parser = script[start : script.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "TEST-profile.xml"
            report_path.write_text(report, encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    parser,
                    report_path,
                    "example.BusinessTest",
                    "passes",
                ],
                capture_output=True,
                check=False,
                text=True,
            )

    def _preflight_environment(self, root: Path) -> dict[str, str]:
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_maven = fake_bin / "mvn"
        fake_maven.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' "
            "'Apache Maven 3.9.14 (996c630dbc656c76214ce58821dcc58be960875b)'\n"
            "printf '%s\\n' 'Java version: 17.0.15, vendor: test'\n",
            encoding="utf-8",
        )
        fake_maven.chmod(0o755)
        reactor = root / "pom.xml"
        owning = root / "module" / "pom.xml"
        owning.parent.mkdir()
        reactor.write_text("<project/>\n", encoding="utf-8")
        owning.write_text("<project/>\n", encoding="utf-8")
        module = owning.parent
        return {
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "ROUTECONTRACT_EXPECTED_OUTCOME": "review",
            "ROUTECONTRACT_REACTOR_POM": os.fspath(reactor),
            "ROUTECONTRACT_OWNING_POM": os.fspath(owning),
            "ROUTECONTRACT_REACTOR_SELECTOR": "example:module",
            "ROUTECONTRACT_PROFILE_OFF_REPORT": os.fspath(
                module / "target" / "profile.xml"
            ),
            "ROUTECONTRACT_PROFILE_OFF_CLASS": "example.BusinessTest",
            "ROUTECONTRACT_PROFILE_OFF_METHOD": "passes",
            "ROUTECONTRACT_TEST_CLASS": "example.ContractTest",
            "ROUTECONTRACT_TEST_METHOD": "matches",
            "ROUTECONTRACT_CANDIDATE_PATH": os.fspath(
                module / "target" / "candidate.json"
            ),
            "ROUTECONTRACT_APPROVED_PATH": os.fspath(
                module / "src" / "approved.json"
            ),
            "ROUTECONTRACT_SUREFIRE_REPORT": os.fspath(
                module / "target" / "selected.xml"
            ),
        }

    def test_shell_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", SCRIPT],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_requires_explicit_inputs_before_any_project_command(self) -> None:
        completed = subprocess.run(
            ["bash", SCRIPT],
            capture_output=True,
            check=False,
            env={"PATH": os.environ["PATH"]},
            text=True,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "required environment variable is missing: ROUTECONTRACT_EXPECTED_OUTCOME",
            completed.stderr,
        )

    def test_baseline_is_read_only_and_modes_are_explicit(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("review|matched", text)
        self.assertIn('approved_identity="$(file_identity "$ROUTECONTRACT_APPROVED_PATH")"', text)
        self.assertIn("approved manifest changed during verification", text)
        self.assertIn("review outcome requires an absent approved manifest", text)
        self.assertIn("review run created an approved manifest", text)
        self.assertIn("review run created an approved-manifest symlink", text)
        for forbidden in (
            'cp "$ROUTECONTRACT_CANDIDATE_PATH" "$ROUTECONTRACT_APPROVED_PATH"',
            'mv "$ROUTECONTRACT_CANDIDATE_PATH" "$ROUTECONTRACT_APPROVED_PATH"',
            'rm -f "$ROUTECONTRACT_APPROVED_PATH"',
        ):
            self.assertNotIn(forbidden, text)

    def test_evidence_paths_are_normalized_confined_and_symlink_safe(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for required in (
            "must be an absolute normalized path",
            "path == root or not path.is_relative_to(root)",
            "ancestor.is_symlink()",
            "path.resolve(strict=True).is_relative_to(root.resolve(strict=True))",
            '"profile-off Surefire report" regular',
            '"fresh candidate" regular',
            '"selected-test Surefire report" regular',
            "approved manifest must stay outside Maven target",
            "profile-off report, candidate, and selected-test report must be distinct",
            'assert_absent_path "$ROUTECONTRACT_PROFILE_OFF_REPORT" "profile-off report"',
            'assert_absent_path "$ROUTECONTRACT_CANDIDATE_PATH" "pre-test candidate"',
            'assert_absent_path "$ROUTECONTRACT_SUREFIRE_REPORT" "pre-test selected-test report"',
        ):
            self.assertIn(required, text)

    def test_public_failures_do_not_echo_raw_maven_logs(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("tail -n", text)
        self.assertNotIn("Maven log tail", text)
        self.assertIn("Maven output was not echoed because application logs can contain sensitive data", text)

    def test_rejects_dotdot_evidence_path_before_project_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self._preflight_environment(root)
            env["ROUTECONTRACT_PROFILE_OFF_REPORT"] = os.fspath(
                root / "module" / "target" / ".." / "outside.xml"
            )
            completed = subprocess.run(
                ["bash", SCRIPT],
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "profile-off report must be an absolute normalized path",
            completed.stderr,
        )

    def test_rejects_stale_evidence_before_project_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self._preflight_environment(root)
            profile = Path(env["ROUTECONTRACT_PROFILE_OFF_REPORT"])
            profile.parent.mkdir()
            profile.write_text("stale\n", encoding="utf-8")
            completed = subprocess.run(
                ["bash", SCRIPT],
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("profile-off report must start absent", completed.stderr)

    def test_verifies_profile_off_graph_artifact_and_exact_test_result(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for required in (
            "profile-off build unexpectedly resolved RouteContract",
            "no Maven dependency coordinates were parsed",
            "expected {cardinality} {qualifier}unclassified JAR dependency",
            '"prefix": prefix',
            '"depth": depth',
            'coordinate["type"] == "jar"',
            'coordinate["classifier"] is None',
            'coordinate["scope"] in allowed_scopes',
            'coordinate["depth"] == 1',
            'allowed_scopes={"test"}',
            'allowed_scopes={"compile", "runtime", "test"}',
            "expected exactly one dependency-tree plugin section and one project root",
            "FasterXML Jackson dependencies must be unclassified JARs in an allowed scope",
            '("net.minidev", "json-smart", "2.4.10")',
            '("net.minidev", "accessors-smart", "2.4.9")',
            'jackson_versions != {"2.18.9"}',
            '("org.locationtech.jts.io", "jts-io-common")',
            '("com.google.protobuf", "protobuf-java")',
            "cached RouteContract JAR hash mismatch",
            "the exact selected Surefire testcase did not run once",
            "review run did not have the exact missing-baseline failure",
            "ROUTECONTRACT_EXTERNAL_MAVEN outcome=%s VERIFIED",
        ):
            self.assertIn(required, text)

    def test_graph_parser_accepts_structurally_valid_dependency_tree(self) -> None:
        completed = self._run_graph_parser(VALID_GRAPH)
        self.assertEqual(0, completed.returncode, completed.stderr)
        without_minidev = "\n".join(
            line for line in VALID_GRAPH.splitlines() if "net.minidev:" not in line
        )
        completed = self._run_graph_parser(without_minidev + "\n")
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_graph_parser_rejects_disallowed_structure_and_scopes(self) -> None:
        mutations = {
            "RouteContract compile scope": VALID_GRAPH.replace(
                "routecontract-shardingsphere-5.5:jar:0.1.0:test",
                "routecontract-shardingsphere-5.5:jar:0.1.0:compile",
            ),
            "JDBC provided scope": VALID_GRAPH.replace(
                "shardingsphere-jdbc:jar:5.5.3:compile",
                "shardingsphere-jdbc:jar:5.5.3:provided",
            ),
            "JDBC classifier": VALID_GRAPH.replace(
                "shardingsphere-jdbc:jar:5.5.3:compile",
                "shardingsphere-jdbc:jar:tests:5.5.3:compile",
            ),
            "JDBC pom type": VALID_GRAPH.replace(
                "shardingsphere-jdbc:jar:5.5.3:compile",
                "shardingsphere-jdbc:pom:5.5.3:compile",
            ),
            "JDBC transitive depth": VALID_GRAPH.replace(
                "[INFO] +- org.apache.shardingsphere:shardingsphere-jdbc",
                "[INFO] |  +- org.apache.shardingsphere:shardingsphere-jdbc",
            ),
            "Calcite provided scope": VALID_GRAPH.replace(
                "calcite-core:jar:1.42.0:compile",
                "calcite-core:jar:1.42.0:provided",
            ),
            "Calcite classifier": VALID_GRAPH.replace(
                "calcite-core:jar:1.42.0:compile",
                "calcite-core:jar:tests:1.42.0:compile",
            ),
            "Calcite pom type": VALID_GRAPH.replace(
                "calcite-core:jar:1.42.0:compile",
                "calcite-core:pom:1.42.0:compile",
            ),
            "minidev provided scope": VALID_GRAPH.replace(
                "json-smart:jar:2.4.10:runtime",
                "json-smart:jar:2.4.10:provided",
            ),
            "minidev classifier": VALID_GRAPH.replace(
                "json-smart:jar:2.4.10:runtime",
                "json-smart:jar:tests:2.4.10:runtime",
            ),
            "minidev pom type": VALID_GRAPH.replace(
                "json-smart:jar:2.4.10:runtime",
                "json-smart:pom:2.4.10:runtime",
            ),
            "minidev wrong version": VALID_GRAPH.replace(
                "json-smart:jar:2.4.10:runtime",
                "json-smart:jar:2.4.11:runtime",
            ),
            "minidev duplicate": VALID_GRAPH.replace(
                "[INFO] |  +- net.minidev:json-smart:jar:2.4.10:runtime",
                "[INFO] |  +- net.minidev:json-smart:jar:2.4.10:runtime\n"
                "[INFO] |  +- net.minidev:json-smart:jar:2.4.10:runtime",
            ),
            "Jackson provided scope": VALID_GRAPH.replace(
                "jackson-databind:jar:2.18.9:compile",
                "jackson-databind:jar:2.18.9:provided",
            ),
            "Jackson classifier": VALID_GRAPH.replace(
                "jackson-databind:jar:2.18.9:compile",
                "jackson-databind:jar:tests:2.18.9:compile",
            ),
            "Jackson pom type": VALID_GRAPH.replace(
                "jackson-databind:jar:2.18.9:compile",
                "jackson-databind:pom:2.18.9:compile",
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
                "[INFO] +- org.apache.calcite:calcite-core",
                "[INFO] org.apache.calcite:calcite-core",
            ),
        }
        for name, graph in mutations.items():
            with self.subTest(name=name):
                completed = self._run_graph_parser(graph)
                self.assertNotEqual(0, completed.returncode)

    def test_profile_off_rejects_failure_ignored_suite(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(2, script.count("-Dmaven.test.failure.ignore=false"))
        passing = (
            '<testsuite tests="1" failures="0" errors="0" skipped="0">'
            '<testcase classname="example.BusinessTest" name="passes"/>'
            "</testsuite>"
        )
        completed = self._run_profile_parser(passing)
        self.assertEqual(0, completed.returncode, completed.stderr)
        failing_suite = (
            '<testsuite tests="2" failures="1" errors="0" skipped="0">'
            '<testcase classname="example.BusinessTest" name="passes"/>'
            '<testcase classname="example.OtherTest" name="fails">'
            '<failure message="boom"/>'
            "</testcase></testsuite>"
        )
        completed = self._run_profile_parser(failing_suite)
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("suite contains a failure or error", completed.stderr)


if __name__ == "__main__":
    unittest.main()
