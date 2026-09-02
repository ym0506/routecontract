import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "verify-maven-split-artifact-consumer.py"
SPEC = importlib.util.spec_from_file_location("verify_maven_split_consumer", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MavenSplitArtifactConsumerVerifierTest(unittest.TestCase):
    def test_ci_runs_exact_maven_verifier_with_atomic_evidence_capture(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('MAVEN_BIN="${MAVEN_HOME}/bin/mvn"', workflow)
        self.assertIn(
            "python3 -I scripts/verify-maven-split-artifact-consumer.py "
            '> "${partial}"',
            workflow,
        )
        self.assertIn('mv "${partial}" "${summary}"', workflow)
        self.assertIn(
            "build/ci-evidence/maven-split-consumer-summary.txt", workflow
        )

    def test_regular_executable_accepts_only_absolute_non_symlink_file(self):
        with tempfile.TemporaryDirectory(prefix="routecontract-maven-tool-") as temporary:
            directory = Path(temporary).resolve()
            executable = directory / "mvn"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            self.assertEqual(executable, MODULE.regular_executable(executable, "Maven"))

            with self.assertRaisesRegex(MODULE.VerificationError, "absolute path"):
                MODULE.regular_executable(Path("mvn"), "Maven")

            link = directory / "mvn-link"
            link.symlink_to(executable)
            with self.assertRaisesRegex(MODULE.VerificationError, "non-symlink"):
                MODULE.regular_executable(link, "Maven")

    def test_clean_environment_removes_all_jvm_and_maven_injection_variables(self):
        unsafe = {
            "JAVA_TOOL_OPTIONS": "-javaagent:unexpected.jar",
            "JDK_JAVA_OPTIONS": "--patch-module=java.base=unexpected",
            "_JAVA_OPTIONS": "-Dunexpected=true",
            "MAVEN_ARGS": "-DskipTests",
            "MAVEN_CONFIG": "/unreviewed/config",
            "MAVEN_OPTS": "-Dmaven.ext.class.path=unexpected.jar",
        }
        with mock.patch.dict(os.environ, {**unsafe, "KEEP_ME": "yes"}, clear=True):
            environment = MODULE.clean_environment(Path("/reviewed/jdk17"))

        for name in unsafe:
            self.assertNotIn(name, environment)
        self.assertEqual("/reviewed/jdk17", environment["JAVA_HOME"])
        self.assertEqual("true", environment["MAVEN_SKIP_RC"])
        self.assertEqual("yes", environment["KEEP_ME"])

    def test_run_is_noninteractive_and_fails_on_unexpected_return_code(self):
        completed = subprocess.CompletedProcess(["tool"], 1, stdout="failed safely\n")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as invoked:
            with self.assertRaises(MODULE.VerificationError) as raised:
                MODULE.run(
                    ["tool"],
                    cwd=ROOT,
                    environment={},
                    expect_success=True,
                )

        self.assertIn("expected success", str(raised.exception))
        self.assertIn("failed safely", str(raised.exception))

        self.assertEqual(subprocess.DEVNULL, invoked.call_args.kwargs["stdin"])
        self.assertEqual(subprocess.PIPE, invoked.call_args.kwargs["stdout"])
        self.assertEqual(subprocess.STDOUT, invoked.call_args.kwargs["stderr"])
        self.assertEqual(
            MODULE.COMMAND_TIMEOUT_SECONDS, invoked.call_args.kwargs["timeout"]
        )
        self.assertEqual("strict", invoked.call_args.kwargs["errors"])

    def test_maven_command_pins_isolated_settings_cache_checksums_and_stage(self):
        command = MODULE.maven_command(
            Path("/reviewed/maven/bin/mvn"),
            Path("/checkout/consumer/pom.xml"),
            Path("/checkout/consumer/settings.xml"),
            Path("/private/tmp/fresh-m2"),
            Path("/private/tmp/staging"),
            "routecontract-552,wrong-non-anchor",
            ["clean", "verify"],
        )

        self.assertEqual("/reviewed/maven/bin/mvn", command[0])
        self.assertIn("--strict-checksums", command)
        self.assertEqual(1, command.count("--settings"))
        self.assertEqual(1, command.count("--global-settings"))
        self.assertIn("-Dmaven.repo.local=/private/tmp/fresh-m2", command)
        self.assertIn(
            "-Droutecontract.repositoryUrl=file:///private/tmp/staging", command
        )
        self.assertIn("-Proutecontract-552,wrong-non-anchor", command)
        self.assertEqual(["clean", "verify"], command[-2:])

    def test_exact_output_line_rejects_prefix_suffix_and_inline_mentions(self):
        expected = "ROUTECONTRACT_MAVEN_SPLIT_RUNTIME_VERIFIED version=5.5.3"
        MODULE.require_exact_output_line(f"noise\n{expected}\n", expected, "lane")

        for ambiguous in (
            f"[INFO] {expected}\n",
            f"{expected} adapter=unexpected\n",
            f"a test expected {expected} but did not execute it\n",
        ):
            with self.subTest(ambiguous=ambiguous):
                with self.assertRaisesRegex(
                    MODULE.VerificationError, "omitted exact output line"
                ):
                    MODULE.require_exact_output_line(ambiguous, expected, "lane")

    def test_staged_origin_requires_exact_jar_and_pom_markers(self):
        with tempfile.TemporaryDirectory(prefix="routecontract-maven-origin-") as temporary:
            repository = Path(temporary).resolve()
            module = "routecontract-core"
            marker = (
                repository
                / MODULE.GROUP_PATH
                / module
                / "0.2.0"
                / "_remote.repositories"
            )
            marker.parent.mkdir(parents=True)
            marker.write_text(
                "#NOTE: generated by Maven Resolver\n"
                f"{module}-0.2.0.jar>routecontract-staged=\n"
                f"{module}-0.2.0.pom>routecontract-staged=\n",
                encoding="utf-8",
            )

            MODULE.assert_staged_origin(repository, module)

            marker.write_text(
                f"{module}-0.2.0.jar>routecontract-staged=\n"
                f"{module}-0.2.0.pom>central=\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.VerificationError, "unambiguously.*missing=.*unexpected="
            ):
                MODULE.assert_staged_origin(repository, module)

    def test_staged_origin_rejects_an_additional_repository_for_same_payload(self):
        with tempfile.TemporaryDirectory(prefix="routecontract-maven-origin-") as temporary:
            repository = Path(temporary).resolve()
            module = "routecontract-shardingsphere-5.5.2"
            marker = (
                repository
                / MODULE.GROUP_PATH
                / module
                / "0.2.0"
                / "_remote.repositories"
            )
            marker.parent.mkdir(parents=True)
            marker.write_text(
                f"{module}-0.2.0.jar>routecontract-staged=\n"
                f"{module}-0.2.0.jar>central=\n"
                f"{module}-0.2.0.pom>routecontract-staged=\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MODULE.VerificationError, "unexpected=.*central"
            ):
                MODULE.assert_staged_origin(repository, module)

    def test_staged_origin_rejects_symlink_marker(self):
        with tempfile.TemporaryDirectory(prefix="routecontract-maven-origin-") as temporary:
            repository = Path(temporary).resolve()
            module = "routecontract-core"
            marker = (
                repository
                / MODULE.GROUP_PATH
                / module
                / "0.2.0"
                / "_remote.repositories"
            )
            marker.parent.mkdir(parents=True)
            target = repository / "unreviewed-marker"
            target.write_text(
                f"{module}-0.2.0.jar>routecontract-staged=\n"
                f"{module}-0.2.0.pom>routecontract-staged=\n",
                encoding="utf-8",
            )
            marker.symlink_to(target)

            with self.assertRaisesRegex(
                MODULE.VerificationError, "regular non-symlink"
            ):
                MODULE.assert_staged_origin(repository, module)

    def test_toolchain_rejects_wrong_java_or_maven_version(self):
        common = {
            "maven": Path("/reviewed/mvn"),
            "java_home": Path("/reviewed/jdk"),
            "root": ROOT,
            "environment": {},
        }
        with mock.patch.object(
            MODULE, "regular_executable", return_value=Path("/reviewed/jdk/bin/java")
        ), mock.patch.object(
            MODULE,
            "run",
            side_effect=[
                'openjdk version "21.0.2"\n',
            ],
        ):
            with self.assertRaisesRegex(MODULE.VerificationError, "JDK 17"):
                MODULE.verify_toolchain(**common)

        with mock.patch.object(
            MODULE, "regular_executable", return_value=Path("/reviewed/jdk/bin/java")
        ), mock.patch.object(
            MODULE,
            "run",
            side_effect=[
                'openjdk version "17.0.12"\n',
                "Apache Maven 3.9.13 (revision)\nJava version: 17.0.12\n",
            ],
        ):
            with self.assertRaisesRegex(MODULE.VerificationError, "3.9.14"):
                MODULE.verify_toolchain(**common)


if __name__ == "__main__":
    unittest.main()
