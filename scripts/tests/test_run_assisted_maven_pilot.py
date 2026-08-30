from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "run-assisted-maven-pilot.py"
EXAMPLE = (
    REPOSITORY_ROOT
    / "examples"
    / "maven-pilot"
    / "assisted-pilot.example.json"
)


def load_module():
    specification = importlib.util.spec_from_file_location(
        "run_assisted_maven_pilot", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise AssertionError("unable to load assisted Maven pilot wrapper")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class AssistedMavenPilotWrapperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def _project(self, root: Path, owning_module: str = "integration-tests") -> Path:
        project = root / "project"
        project.mkdir()
        pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>integration-tests</artifactId>
  <version>1</version>
</project>
"""
        (project / "pom.xml").write_text(pom, encoding="utf-8")
        owning = project if owning_module == "." else project / owning_module
        owning.mkdir(exist_ok=True)
        if owning != project:
            (owning / "pom.xml").write_text(pom, encoding="utf-8")
        return project.resolve(strict=True)

    @contextlib.contextmanager
    def _fake_isolation(self, invocation, _ambient):
        with tempfile.TemporaryDirectory() as temporary:
            yield {
                "PATH": "/isolated/bin",
                "HOME": "/isolated/home",
                "TMPDIR": os.fspath(Path(temporary).resolve(strict=True)),
                "MAVEN_ARGS": "--settings /isolated/settings.xml",
                **invocation.routecontract_environment,
            }

    def _config(
        self,
        root: Path,
        project: Path,
        **overrides: object,
    ) -> Path:
        values: dict[str, object] = {
            "projectRoot": os.fspath(project),
            "owningModule": "integration-tests",
            "reactorSelector": "integration-tests/pom.xml",
            "profileOffTest": "example.BusinessTest#routeContractIsAbsent",
            "pilotTest": "example.RouteContractTest#capturesCandidate",
            "operationId": "orders.find-by-user-id",
        }
        values.update(overrides)
        config = root / "pilot.json"
        config.write_text(json.dumps(values), encoding="utf-8")
        return config.resolve(strict=True)

    def test_derives_exact_twelve_environment_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            invocation = self.module.prepare_invocation(config, "review", {})

        owning = project / "integration-tests"
        self.assertEqual(project, invocation.cwd)
        self.assertEqual(
            {
                "ROUTECONTRACT_EXPECTED_OUTCOME": "review",
                "ROUTECONTRACT_REACTOR_POM": os.fspath(project / "pom.xml"),
                "ROUTECONTRACT_OWNING_POM": os.fspath(owning / "pom.xml"),
                "ROUTECONTRACT_REACTOR_SELECTOR": "integration-tests/pom.xml",
                "ROUTECONTRACT_PROFILE_OFF_REPORT": os.fspath(
                    owning
                    / "target"
                    / "surefire-reports"
                    / "TEST-example.BusinessTest.xml"
                ),
                "ROUTECONTRACT_PROFILE_OFF_CLASS": "example.BusinessTest",
                "ROUTECONTRACT_PROFILE_OFF_METHOD": "routeContractIsAbsent",
                "ROUTECONTRACT_TEST_CLASS": "example.RouteContractTest",
                "ROUTECONTRACT_TEST_METHOD": "capturesCandidate",
                "ROUTECONTRACT_CANDIDATE_PATH": os.fspath(
                    owning
                    / "target"
                    / "routecontract"
                    / "orders.find-by-user-id.candidate.json"
                ),
                "ROUTECONTRACT_APPROVED_PATH": os.fspath(
                    owning
                    / "src"
                    / "routeContractPilot"
                    / "resources"
                    / "route-contracts"
                    / "orders.find-by-user-id.json"
                ),
                "ROUTECONTRACT_SUREFIRE_REPORT": os.fspath(
                    owning
                    / "target"
                    / "surefire-reports"
                    / "TEST-example.RouteContractTest.xml"
                ),
            },
            invocation.routecontract_environment,
        )
        self.assertEqual(12, len(invocation.routecontract_environment))

    def test_root_module_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root, owning_module=".")
            config = self._config(
                root, project, owningModule=".", reactorSelector="pom.xml"
            )
            invocation = self.module.prepare_invocation(config, "review", {})
        self.assertEqual(
            os.fspath(project / "pom.xml"),
            invocation.routecontract_environment["ROUTECONTRACT_OWNING_POM"],
        )

    def test_main_uses_scrubbed_environment_and_requires_exact_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            ambient = {
                "PATH": os.environ.get("PATH", ""),
                "SAFE": "must-not-cross-the-boundary",
                "MAVEN_ARGS": "--fail-never",
                "JAVA_TOOL_OPTIONS": "-javaagent:poison.jar",
            }
            completed = self.module.VerifierResult(
                0, b"ROUTECONTRACT_EXTERNAL_MAVEN outcome=review VERIFIED\n", b""
            )
            with mock.patch.dict(os.environ, ambient, clear=True), mock.patch.object(
                self.module, "_run_verifier", return_value=completed
            ) as runner, mock.patch.object(
                self.module,
                "_isolated_maven_environment",
                side_effect=self._fake_isolation,
            ):
                result = self.module.main(
                    ["--config", os.fspath(config), "--expected-outcome", "review"]
                )
        self.assertEqual(0, result)
        self.assertEqual(1, runner.call_count)
        args, kwargs = runner.call_args
        self.assertEqual(project, args[0].cwd)
        child_environment = args[1]
        self.assertNotIn("SAFE", child_environment)
        self.assertNotIn("JAVA_TOOL_OPTIONS", child_environment)
        self.assertNotEqual("--fail-never", child_environment["MAVEN_ARGS"])
        self.assertEqual(
            set(self.module.ROUTECONTRACT_ENVIRONMENT_KEYS),
            {
                key
                for key in child_environment
                if key.startswith("ROUTECONTRACT_")
            },
        )

    def test_rejects_duplicate_unknown_missing_nonstring_and_invalid_json(self) -> None:
        valid = {
            "projectRoot": "/absolute/project",
            "owningModule": "module",
            "reactorSelector": "module/pom.xml",
            "profileOffTest": "example.BusinessTest#passes",
            "pilotTest": "example.ContractTest#captures",
            "operationId": "orders.find",
        }
        cases: dict[str, bytes] = {
            "duplicate": (
                '{"projectRoot":"/one","projectRoot":"/two",'
                '"owningModule":"module","reactorSelector":"module/pom.xml",'
                '"profileOffTest":"example.BusinessTest#passes",'
                '"pilotTest":"example.ContractTest#captures",'
                '"operationId":"orders.find"}'
            ).encode(),
            "unknown": json.dumps({**valid, "extra": "no"}).encode(),
            "missing": json.dumps(
                {key: value for key, value in valid.items() if key != "operationId"}
            ).encode(),
            "nonstring": json.dumps({**valid, "operationId": 7}).encode(),
            "invalid utf8": b"\xff",
            "control": json.dumps({**valid, "operationId": "bad\nvalue"}).encode(),
            "not nfc": json.dumps(
                {**valid, "operationId": "e\N{COMBINING ACUTE ACCENT}"}
            ).encode(),
            "array": b"[]",
        }
        for name, payload in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary).resolve(strict=True) / "config.json"
                path.write_bytes(payload)
                with self.assertRaises(self.module.AssistedPilotError):
                    self.module.load_config(path)

    def test_rejects_oversized_or_symlink_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (self.module.MAX_CONFIG_BYTES + 1))
            with self.assertRaises(self.module.AssistedPilotError):
                self.module.load_config(oversized)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaises(self.module.AssistedPilotError):
                self.module.load_config(link)

    def test_rejects_unsafe_module_selector_test_and_operation_values(self) -> None:
        invalid_values = {
            "owningModule": ("../outside", "/absolute", "a//b", "a\\b", "-module"),
            "reactorSelector": (
                "-am",
                "one,two",
                "!module",
                "example:module;touch",
                "example:$(id)",
                "example:`id`",
            ),
            "profileOffTest": (
                "missingHash",
                "a.Test#one#two",
                "a.Test#method[1]",
                "a.Test#method()",
            ),
            "pilotTest": ("#method", "a.Test#", "a-test.Test#method"),
            "operationId": (
                "../escape",
                ".hidden",
                "bad/name",
                "bad\\name",
                "two..dots",
                "-leading",
            ),
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary).resolve(strict=True)
                    project = self._project(root)
                    config = self._config(root, project, **{field: value})
                    with self.assertRaises(self.module.AssistedPilotError):
                        self.module.prepare_invocation(config, "review", {})

    def test_rejects_same_class_report_collision_and_ambient_routecontract_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(
                root,
                project,
                profileOffTest="example.SameTest#off",
                pilotTest="example.SameTest#pilot",
            )
            with self.assertRaisesRegex(
                self.module.AssistedPilotError, "distinct test classes"
            ):
                self.module.prepare_invocation(config, "review", {})
            config = self._config(root, project)
            with self.assertRaisesRegex(
                self.module.AssistedPilotError, "ambient ROUTECONTRACT_"
            ):
                self.module.prepare_invocation(
                    config, "review", {"ROUTECONTRACT_TEST_CLASS": "injected"}
                )

    def test_rejects_noncanonical_or_symlink_project_paths_and_poms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            link = root / "project-link"
            link.symlink_to(project, target_is_directory=True)
            config = self._config(root, project, projectRoot=os.fspath(link))
            with self.assertRaises(self.module.AssistedPilotError):
                self.module.prepare_invocation(config, "review", {})

    def test_rejects_project_maven_config_and_selector_mismatch(self) -> None:
        for name in ("maven.config", "jvm.config", "extensions.xml"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(strict=True)
                project = self._project(root)
                config = self._config(root, project)
                project_config = project / ".mvn" / name
                project_config.parent.mkdir()
                project_config.write_text("poison\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, f".mvn/{re.escape(name)}"
                ):
                    self.module.prepare_invocation(config, "review", {})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(
                root, project, reactorSelector="other:integration-tests"
            )
            with self.assertRaisesRegex(
                self.module.AssistedPilotError, "owning POM path"
            ):
                self.module.prepare_invocation(config, "review", {})

        for kind in ("symlink", "file", "dangling"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(strict=True)
                project = self._project(root)
                config = self._config(root, project)
                dot_maven = project / ".mvn"
                if kind == "file":
                    dot_maven.write_text("not a directory\n", encoding="utf-8")
                else:
                    target = root / ("maven-config" if kind == "symlink" else "missing")
                    if kind == "symlink":
                        target.mkdir()
                    dot_maven.symlink_to(target, target_is_directory=True)
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "project .mvn"
                ):
                    self.module.prepare_invocation(config, "review", {})

    def test_selector_is_bound_to_pom_path_and_rejects_symlink_pom(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            owning_pom = project / "integration-tests" / "pom.xml"
            owning_pom.write_text(
                """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>${pilot.group}</groupId>
  <artifactId>integration-tests</artifactId>
  <version>1</version>
</project>
""",
                encoding="utf-8",
            )
            config = self._config(root, project)
            invocation = self.module.prepare_invocation(config, "review", {})
            self.assertEqual(
                "integration-tests/pom.xml",
                invocation.routecontract_environment["ROUTECONTRACT_REACTOR_SELECTOR"],
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            owning = project / "integration-tests"
            original = owning / "pom-real.xml"
            (owning / "pom.xml").rename(original)
            (owning / "pom.xml").symlink_to(original)
            config = self._config(root, project)
            with self.assertRaises(self.module.AssistedPilotError):
                self.module.prepare_invocation(config, "review", {})

    def test_rejects_stale_outputs_without_deleting_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            stale = (
                project
                / "integration-tests"
                / "target"
                / "routecontract"
                / "orders.find-by-user-id.candidate.json"
            )
            stale.parent.mkdir(parents=True)
            stale.write_text("stale\n", encoding="utf-8")
            with self.assertRaises(self.module.AssistedPilotError):
                self.module.prepare_invocation(config, "review", {})
            self.assertEqual("stale\n", stale.read_text(encoding="utf-8"))

    def test_review_detects_child_created_baseline_and_does_not_remove_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            invocation = self.module.prepare_invocation(config, "review", {})
            approved = Path(
                invocation.routecontract_environment["ROUTECONTRACT_APPROVED_PATH"]
            )

            def mutate(*_args, **_kwargs):
                approved.parent.mkdir(parents=True)
                approved.write_text("not approved\n", encoding="utf-8")
                return self.module.VerifierResult(
                    0,
                    b"ROUTECONTRACT_EXTERNAL_MAVEN outcome=review VERIFIED\n",
                    b"",
                )

            captured = io.StringIO()
            with mock.patch.object(
                self.module, "_isolated_maven_environment", side_effect=self._fake_isolation
            ), mock.patch.object(self.module, "_run_verifier", side_effect=mutate):
                with contextlib.redirect_stdout(captured):
                    with self.assertRaisesRegex(
                        self.module.AssistedPilotError, "created the approved baseline"
                    ):
                        self.module.execute(invocation, {"PATH": "safe"})
            self.assertEqual("not approved\n", approved.read_text(encoding="utf-8"))
            self.assertEqual("", captured.getvalue())

    def test_matched_detects_child_baseline_mutation_and_preserves_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            approved = (
                project
                / "integration-tests"
                / "src"
                / "routeContractPilot"
                / "resources"
                / "route-contracts"
                / "orders.find-by-user-id.json"
            )
            approved.parent.mkdir(parents=True)
            approved.write_text("approved\n", encoding="utf-8")
            invocation = self.module.prepare_invocation(config, "matched", {})

            def mutate(*_args, **_kwargs):
                approved.write_text("mutated\n", encoding="utf-8")
                return self.module.VerifierResult(
                    0,
                    b"ROUTECONTRACT_EXTERNAL_MAVEN outcome=matched VERIFIED\n",
                    b"",
                )

            with mock.patch.object(
                self.module, "_isolated_maven_environment", side_effect=self._fake_isolation
            ), mock.patch.object(self.module, "_run_verifier", side_effect=mutate):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "approved baseline changed"
                ):
                    self.module.execute(invocation, {"PATH": "safe"})
            self.assertEqual("mutated\n", approved.read_text(encoding="utf-8"))

    def test_matched_rejects_hardlinked_baseline_and_child_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            approved = (
                project
                / "integration-tests"
                / "src"
                / "routeContractPilot"
                / "resources"
                / "route-contracts"
                / "orders.find-by-user-id.json"
            )
            approved.parent.mkdir(parents=True)
            approved.write_text("approved\n", encoding="utf-8")
            extra = root / "extra-link.json"
            os.link(approved, extra)
            with self.assertRaisesRegex(
                self.module.AssistedPilotError, "exactly one hard link"
            ):
                self.module.prepare_invocation(config, "matched", {})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            approved = (
                project
                / "integration-tests"
                / "src"
                / "routeContractPilot"
                / "resources"
                / "route-contracts"
                / "orders.find-by-user-id.json"
            )
            approved.parent.mkdir(parents=True)
            approved.write_text("approved\n", encoding="utf-8")
            invocation = self.module.prepare_invocation(config, "matched", {})
            candidate = invocation.output_paths[1]

            def hardlink_output(*_args, **_kwargs):
                candidate.parent.mkdir(parents=True)
                os.link(approved, candidate)
                return self.module.VerifierResult(
                    0,
                    b"ROUTECONTRACT_EXTERNAL_MAVEN outcome=matched VERIFIED\n",
                    b"",
                )

            with mock.patch.object(
                self.module, "_isolated_maven_environment", side_effect=self._fake_isolation
            ), mock.patch.object(self.module, "_run_verifier", side_effect=hardlink_output):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "exactly one hard link"
                ):
                    self.module.execute(invocation, {"PATH": "safe"})

    def test_handled_term_still_checks_baseline(self) -> None:
        if not hasattr(signal, "SIGTERM"):
            self.skipTest("SIGTERM is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            approved = (
                project
                / "integration-tests"
                / "src"
                / "routeContractPilot"
                / "resources"
                / "route-contracts"
                / "orders.find-by-user-id.json"
            )
            approved.parent.mkdir(parents=True)
            approved.write_text("approved\n", encoding="utf-8")
            invocation = self.module.prepare_invocation(config, "matched", {})

            def terminate(_invocation, _environment, state):
                approved.write_text("mutated before TERM\n", encoding="utf-8")
                state.receive(signal.SIGTERM)
                return self.module.VerifierResult(143, b"", b"")

            with mock.patch.object(
                self.module, "_isolated_maven_environment", side_effect=self._fake_isolation
            ), mock.patch.object(self.module, "_run_verifier", side_effect=terminate):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "approved baseline changed"
                ):
                    self.module.execute(invocation, {"PATH": "safe"})

    def test_successful_leader_with_delayed_writer_is_quiesced_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            fake = root / "fake-verifier.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "(/bin/sh -c 'trap \"\" TERM INT HUP; /bin/sleep 1; "
                "printf \"mutated-after-success\\\\n\" > "
                "\"$ROUTECONTRACT_APPROVED_PATH\"') &\n"
                "printf 'ROUTECONTRACT_EXTERNAL_MAVEN outcome=review VERIFIED\\n'\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake.chmod(0o700)
            private_tmp = root / "private-tmp"
            private_tmp.mkdir(mode=0o700)
            environment = {
                "TMPDIR": os.fspath(private_tmp),
                **invocation.routecontract_environment,
            }
            with mock.patch.object(
                self.module,
                "_materialize_verified_execution_bundle",
                return_value=fake,
            ), mock.patch.object(
                self.module, "PROCESS_SIGNAL_GRACE_SECONDS", 0.1
            ):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "descendant processes"
                ):
                    self.module._run_verifier(
                        invocation,
                        environment,
                        self.module.ProcessSignalState(),
                    )
            time.sleep(1.2)
            self.assertFalse(invocation.approved_path.exists())

    def test_first_hup_is_forwarded_without_injecting_term(self) -> None:
        if not hasattr(signal, "SIGHUP"):
            self.skipTest("SIGHUP is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            signal_file = root / "signal.txt"
            ready_file = root / "ready.txt"
            fake = root / "signal-verifier.py"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import os, signal, time\n"
                "def handled(number, _frame):\n"
                "    with open(os.environ['SIGNAL_FILE'], 'w', encoding='ascii') as out:\n"
                "        out.write(signal.Signals(number).name)\n"
                "    raise SystemExit(0)\n"
                "for item in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):\n"
                "    signal.signal(item, handled)\n"
                "with open(os.environ['READY_FILE'], 'w', encoding='ascii') as out:\n"
                "    out.write('ready')\n"
                "while True:\n"
                "    time.sleep(1)\n",
                encoding="utf-8",
            )
            fake.chmod(0o700)
            private_tmp = root / "private-tmp"
            private_tmp.mkdir(mode=0o700)
            environment = {
                "TMPDIR": os.fspath(private_tmp),
                "SIGNAL_FILE": os.fspath(signal_file),
                "READY_FILE": os.fspath(ready_file),
                **invocation.routecontract_environment,
            }
            state = self.module.ProcessSignalState()
            def send_when_ready():
                deadline = time.monotonic() + 5
                while not ready_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if ready_file.exists():
                    os.kill(os.getpid(), signal.SIGHUP)

            sender = threading.Thread(target=send_when_ready, daemon=True)
            sender.start()
            try:
                with mock.patch.object(
                    self.module,
                    "_materialize_verified_execution_bundle",
                    return_value=fake,
                ), self.module._latched_process_signals(state):
                    self.module._run_verifier(invocation, environment, state)
            finally:
                sender.join(timeout=5)
            self.assertEqual(signal.SIGHUP, state.signal_number)
            self.assertEqual("SIGHUP", signal_file.read_text(encoding="ascii"))

    def test_binary_output_and_combined_output_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            private_tmp = root / "private-tmp"
            private_tmp.mkdir(mode=0o700)
            environment = {
                "TMPDIR": os.fspath(private_tmp),
                **invocation.routecontract_environment,
            }
            fake = root / "binary-verifier.py"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import os\n"
                "os.write(1, b'\\xff')\n"
                "os.write(2, b'\\xfe')\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            fake.chmod(0o700)
            with mock.patch.object(
                self.module,
                "_materialize_verified_execution_bundle",
                return_value=fake,
            ):
                result = self.module._run_verifier(
                    invocation, environment, self.module.ProcessSignalState()
                )
            self.assertEqual((7, b"\xff", b"\xfe"), tuple(result))

            capped = root / "capped-verifier.py"
            capped.write_text(
                f"#!{sys.executable}\n"
                "import os\n"
                "os.write(1, b'a' * 32)\n"
                "os.write(2, b'b' * 32)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            capped.chmod(0o700)
            with mock.patch.object(
                self.module, "MAX_VERIFIER_OUTPUT_BYTES", 64
            ), mock.patch.object(
                self.module,
                "_materialize_verified_execution_bundle",
                return_value=capped,
            ):
                result = self.module._run_verifier(
                    invocation, environment, self.module.ProcessSignalState()
                )
            self.assertEqual(64, len(result.stdout) + len(result.stderr))

            oversized = root / "oversized-verifier.py"
            oversized.write_text(
                f"#!{sys.executable}\n"
                "import os, time\n"
                "os.write(1, b'a' * 33)\n"
                "os.write(2, b'b' * 32)\n"
                "time.sleep(5)\n",
                encoding="utf-8",
            )
            oversized.chmod(0o700)
            with mock.patch.object(
                self.module, "MAX_VERIFIER_OUTPUT_BYTES", 64
            ), mock.patch.object(
                self.module,
                "_materialize_verified_execution_bundle",
                return_value=oversized,
            ):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "output exceeded"
                ):
                    self.module._run_verifier(
                        invocation, environment, self.module.ProcessSignalState()
                    )

    def test_real_term_interrupts_new_session_before_postcheck(self) -> None:
        if not hasattr(signal, "SIGTERM"):
            self.skipTest("SIGTERM is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            fake = root / "sleep-verifier.sh"
            fake.write_text("#!/bin/sh\nexec /bin/sleep 30\n", encoding="utf-8")
            fake.chmod(0o700)
            timer = threading.Timer(
                0.2, lambda: os.kill(os.getpid(), signal.SIGTERM)
            )
            timer.start()
            try:
                with mock.patch.object(
                    self.module,
                    "_isolated_maven_environment",
                    side_effect=self._fake_isolation,
                ), mock.patch.object(
                    self.module,
                    "_materialize_verified_execution_bundle",
                    return_value=fake,
                ):
                    with self.assertRaises(self.module.AssistedPilotInterrupt) as caught:
                        self.module.execute(invocation, {"PATH": "safe"})
            finally:
                timer.cancel()
            self.assertEqual(signal.SIGTERM, caught.exception.signal_number)
            self.assertFalse(invocation.approved_path.exists())

    def test_review_postcheck_rejects_new_symlink_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            outside = root / "outside"
            outside.mkdir()
            (invocation.owning_root / "src").symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaisesRegex(
                self.module.AssistedPilotError, "redirected its path"
            ):
                self.module._assert_baseline_postcondition(invocation)

    def test_second_signal_before_attach_is_forwarded_as_kill(self) -> None:
        state = self.module.ProcessSignalState()
        state.receive(signal.SIGTERM)
        state.receive(signal.SIGINT)
        with mock.patch.object(self.module.os, "killpg") as killpg:
            state.attach(12345)
        killpg.assert_called_once_with(12345, signal.SIGKILL)

    def test_execute_rechecks_replaced_verifier_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            bundle = root / "bundle"
            bundle.mkdir()
            original_verifier = self.module.VERIFIER
            for name in (
                original_verifier.name,
                "install-release-assets.py",
                "prepare_maven_v0_1_2_checksums.py",
            ):
                (bundle / name).write_bytes(original_verifier.with_name(name).read_bytes())
            verifier = (bundle / original_verifier.name).resolve(strict=True)
            with mock.patch.object(self.module, "VERIFIER", verifier):
                invocation = self.module.prepare_invocation(
                    self._config(root, project), "review", {}
                )
                verifier.write_text(
                    "#!/bin/sh\nprintf 'ALTERED_VERIFIER_EXECUTED\\n'\nexit 0\n",
                    encoding="utf-8",
                )
                captured = io.StringIO()
                with mock.patch.object(
                    self.module,
                    "_isolated_maven_environment",
                    side_effect=self._fake_isolation,
                ), contextlib.redirect_stdout(captured):
                    with self.assertRaisesRegex(
                        self.module.AssistedPilotError, "does not match its SHA-256"
                    ):
                        self.module.execute(invocation, {"PATH": "safe"})
            self.assertNotIn("ALTERED_VERIFIER_EXECUTED", captured.getvalue())

    def test_zero_exit_without_exact_external_marker_is_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            captured = io.StringIO()
            with mock.patch.object(
                self.module,
                "_isolated_maven_environment",
                side_effect=self._fake_isolation,
            ), mock.patch.object(
                self.module,
                "_run_verifier",
                return_value=self.module.VerifierResult(0, b"not-the-marker\n", b""),
            ), contextlib.redirect_stdout(captured):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "exact success marker"
                ):
                    self.module.execute(invocation, {"PATH": "safe"})
            self.assertNotIn("ROUTECONTRACT_ASSISTED_MAVEN", captured.getvalue())

    def test_execute_rechecks_maven_configuration_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            invocation = self.module.prepare_invocation(
                self._config(root, project), "review", {}
            )
            outside = root / "outside-mvn"
            outside.mkdir()
            (project / ".mvn").symlink_to(outside, target_is_directory=True)
            with mock.patch.object(
                self.module,
                "_isolated_maven_environment",
                side_effect=self._fake_isolation,
            ), mock.patch.object(self.module, "_run_verifier") as runner:
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "project .mvn"
                ):
                    self.module.execute(invocation, {"PATH": "safe"})
            runner.assert_not_called()

    def test_matched_baseline_check_wins_when_environment_setup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            approved = (
                project
                / "integration-tests"
                / "src"
                / "routeContractPilot"
                / "resources"
                / "route-contracts"
                / "orders.find-by-user-id.json"
            )
            approved.parent.mkdir(parents=True)
            approved.write_text("approved\n", encoding="utf-8")
            invocation = self.module.prepare_invocation(config, "matched", {})

            @contextlib.contextmanager
            def fail_setup(_invocation, _ambient):
                approved.write_text("mutated during setup\n", encoding="utf-8")
                raise self.module.AssistedPilotError("environment setup failed")
                yield {}

            with mock.patch.object(
                self.module,
                "_isolated_maven_environment",
                side_effect=fail_setup,
            ):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "approved baseline changed"
                ):
                    self.module.execute(invocation, {"PATH": "safe"})

    def test_isolated_environment_discards_ambient_maven_and_jvm_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            project = self._project(root)
            config = self._config(root, project)
            invocation = self.module.prepare_invocation(config, "review", {})
            fake_java_home = root / "jdk"
            fake_java = fake_java_home / "bin" / "java"
            fake_java.parent.mkdir(parents=True)
            fake_java.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_java.chmod(0o700)
            executable = Path(sys.executable).resolve(strict=True)

            def fake_download(_curl, destination):
                destination.write_bytes(b"archive")

            def fake_extract(_archive, destination):
                home = destination / self.module.MAVEN_TOP_DIRECTORY
                launcher = home / "bin" / "mvn"
                launcher.parent.mkdir(parents=True)
                launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                launcher.chmod(0o700)
                return home

            ambient = {
                "PATH": "/attacker/bin",
                "HOME": "/attacker/home",
                "MAVEN_ARGS": "--fail-never",
                "MAVEN_OPTS": "-javaagent:poison.jar",
                "JAVA_TOOL_OPTIONS": "-javaagent:poison.jar",
                "JDK_JAVA_OPTIONS": "-javaagent:poison.jar",
                "BASH_ENV": "/attacker/bash-env",
                "ENV": "/attacker/sh-env",
                "SAFE": "also-not-allowlisted",
            }
            with mock.patch.object(
                self.module,
                "_canonical_executable",
                side_effect=lambda name, _path: (
                    executable if name == "curl" else fake_java
                ),
            ), mock.patch.object(
                self.module, "_java_home", return_value=fake_java_home
            ), mock.patch.object(
                self.module, "_download_maven_archive", side_effect=fake_download
            ), mock.patch.object(
                self.module, "_extract_maven_archive", side_effect=fake_extract
            ):
                with self.module._isolated_maven_environment(
                    invocation, ambient
                ) as environment:
                    temporary_root = Path(environment["HOME"]).parent
                    self.assertNotIn("/attacker", environment["PATH"])
                    for key in (
                        "JAVA_TOOL_OPTIONS",
                        "JDK_JAVA_OPTIONS",
                        "BASH_ENV",
                        "ENV",
                        "SAFE",
                    ):
                        self.assertNotIn(key, environment)
                    self.assertNotEqual("--fail-never", environment["MAVEN_ARGS"])
                    self.assertNotIn("poison", environment["MAVEN_OPTS"])
                    self.assertEqual("true", environment["MAVEN_SKIP_RC"])
                    self.assertEqual(os.fspath(project), environment["MAVEN_BASEDIR"])
                    self.assertIn("--global-settings", environment["MAVEN_ARGS"])
                    self.assertIn("--global-toolchains", environment["MAVEN_ARGS"])
                    self.assertEqual(
                        set(self.module.ROUTECONTRACT_ENVIRONMENT_KEYS),
                        {
                            key
                            for key in environment
                            if key.startswith("ROUTECONTRACT_")
                        },
                    )
            self.assertFalse(temporary_root.exists())

    def test_maven_archive_hash_and_member_paths_fail_closed(self) -> None:
        executable = Path(sys.executable).resolve(strict=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            destination = root / "maven.tgz"

            def write_bad_archive(arguments, **_kwargs):
                output = Path(arguments[arguments.index("--output") + 1])
                output.write_bytes(b"not the pinned archive")
                return subprocess.CompletedProcess(arguments, 0)

            with mock.patch.object(
                self.module.subprocess, "run", side_effect=write_bad_archive
            ):
                with self.assertRaisesRegex(
                    self.module.AssistedPilotError, "pinned SHA-512"
                ):
                    self.module._download_maven_archive(executable, destination)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            archive = root / "unsafe.tgz"
            with tarfile.open(archive, "w:gz") as opened:
                member = tarfile.TarInfo(
                    f"{self.module.MAVEN_TOP_DIRECTORY}/../outside"
                )
                member.size = 1
                opened.addfile(member, io.BytesIO(b"x"))
            destination = root / "out"
            destination.mkdir()
            with self.assertRaisesRegex(
                self.module.AssistedPilotError, "unsafe member path"
            ):
                self.module._extract_maven_archive(archive, destination)

    def test_verifier_hash_is_pinned_to_current_reviewed_bytes(self) -> None:
        digest = hashlib.sha256(self.module.VERIFIER.read_bytes()).hexdigest()
        self.assertEqual(self.module.EXPECTED_VERIFIER_SHA256, digest)

    def test_example_and_public_docs_surface_the_one_command_boundary(self) -> None:
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(self.module.CONFIG_KEYS, frozenset(example))
        self.assertEqual("/absolute/path/to/your-repository", example["projectRoot"])
        fixture_readme = (
            REPOSITORY_ROOT / "examples" / "maven-pilot" / "README.md"
        ).read_text(encoding="utf-8")
        for required in (
            "run-assisted-maven-pilot.py",
            "--expected-outcome review",
            "--expected-outcome matched",
            "never creates, copies, replaces, or deletes the approved baseline",
            "six-field JSON",
            "integration-tests/pom.xml",
            "those of the three selected `target` evidence files that exist",
            self.module.MAVEN_ARCHIVE_SHA512,
            ".mvn/maven.config",
            "private home",
            "not a security sandbox",
            "setsid`/`setpgid",
        ):
            self.assertIn(required, fixture_readme)
        for readme in ("README.md", "README.en.md"):
            text = (REPOSITORY_ROOT / readme).read_text(encoding="utf-8")
            self.assertIn(
                "examples/maven-pilot/assisted-pilot.example.json", text
            )


if __name__ == "__main__":
    unittest.main()
