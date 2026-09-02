import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts/verify-gradle-split-artifact-consumer.py"
SPEC = importlib.util.spec_from_file_location("verify_gradle_split", TOOL)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def lane_output(lane):
    return "\n".join(
        (
            "ROUTECONTRACT_GRADLE_SPLIT_GRAPH_VERIFIED "
            f"adapter={lane['adapter']} routeContractVersion=0.2.0 "
            f"shardingSphereVersion={lane['version']} "
            f"shardingSphereComponents={lane['components']}",
            "ROUTECONTRACT_GRADLE_WRONG_NON_ANCHOR_REJECTED "
            f"module=shardingsphere-infra-common requested={lane['other']} "
            f"expected={lane['version']}",
            "ROUTECONTRACT_GRADLE_DUAL_ADAPTER_REJECTED "
            "order=5.5.2-then-5.5.3 "
            "capability=io.github.ym0506.routecontract:"
            "routecontract-shardingsphere-hook-adapter:1",
            "ROUTECONTRACT_GRADLE_DUAL_ADAPTER_REJECTED "
            "order=5.5.3-then-5.5.2 "
            "capability=io.github.ym0506.routecontract:"
            "routecontract-shardingsphere-hook-adapter:1",
            f"ROUTECONTRACT_GRADLE_SPLIT_RUNTIME_VERIFIED version={lane['version']}",
            "BUILD SUCCESSFUL",
        )
    )


class VerifyGradleSplitArtifactConsumerTest(unittest.TestCase):
    def test_ci_runs_verifier_with_atomic_evidence_capture(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 60", workflow)
        self.assertIn(
            "python3 -I scripts/verify-gradle-split-artifact-consumer.py "
            '> "${partial}"',
            workflow,
        )
        self.assertIn('mv "${partial}" "${summary}"', workflow)
        self.assertIn(
            "build/ci-evidence/gradle-split-consumer-summary.txt", workflow
        )

    def test_accepts_both_exact_lane_receipts(self):
        for lane in VERIFY.LANES.values():
            VERIFY.validate_lane_output(lane_output(lane), lane)

    def test_rejects_missing_duplicate_or_wrong_graph_evidence(self):
        lane = VERIFY.LANES["552"]
        valid = lane_output(lane)
        graph = valid.splitlines()[0]
        cases = (
            valid.replace(graph + "\n", "", 1),
            valid.replace(graph, graph + "\n" + graph, 1),
            valid.replace("shardingSphereComponents=48", "shardingSphereComponents=47"),
            valid + "\nDependency verification failed",
        )
        for output in cases:
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_lane_output(output, lane)

    def test_gradle_command_is_strict_uncached_and_rerun(self):
        command = VERIFY.gradle_command(
            Path("/repo/gradlew"),
            Path("/repo/examples/fixture"),
            Path("/tmp/project-cache"),
            "5.5.3",
            ["clean", "check"],
        )
        self.assertIn("--dependency-verification=strict", command)
        self.assertIn("--no-build-cache", command)
        self.assertIn("--no-configuration-cache", command)
        self.assertIn("--rerun-tasks", command)
        self.assertIn("-ProutecontractAdapterVersion=5.5.3", command)
        self.assertEqual(["clean", "check"], command[-2:])

    def test_clean_environment_removes_gradle_and_java_injection(self):
        names = {
            "GRADLE_OPTS": "-Dunsafe=true",
            "JAVA_OPTS": "-Dunsafe=true",
            "JAVA_TOOL_OPTIONS": "-Dunsafe=true",
            "JDK_JAVA_OPTIONS": "-Dunsafe=true",
            "_JAVA_OPTIONS": "-Dunsafe=true",
            "ORG_GRADLE_PROJECT_routecontractAdapterVersion": "5.5.1",
        }
        previous = {name: os.environ.get(name) for name in names}
        try:
            os.environ.update(names)
            environment = VERIFY.clean_environment(Path("/jdk17"), Path("/gradle-home"))
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        for name in names:
            self.assertNotIn(name, environment)
        self.assertEqual("/jdk17", environment["JAVA_HOME"])
        self.assertEqual("/gradle-home", environment["GRADLE_USER_HOME"])

    def test_corrupts_only_exact_executor_jar_checksum(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">
  <configuration><verify-metadata>true</verify-metadata></configuration>
  <components>
    <component group="org.apache.shardingsphere" name="shardingsphere-infra-executor" version="5.5.2">
      <artifact name="shardingsphere-infra-executor-5.5.2.jar"><sha256 value="%s"/></artifact>
      <artifact name="shardingsphere-infra-executor-5.5.2.pom"><sha256 value="%s"/></artifact>
    </component>
  </components>
</verification-metadata>
""" % ("a" * 64, "b" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            metadata = Path(temporary) / "verification-metadata.xml"
            metadata.write_text(xml, encoding="utf-8")
            original = VERIFY.corrupt_executor_checksum(metadata, "5.5.2")
            rendered = metadata.read_text(encoding="utf-8")
        self.assertEqual("a" * 64, original)
        self.assertIn('value="' + "0" * 64 + '"', rendered)
        self.assertIn('value="' + "b" * 64 + '"', rendered)

    def test_fixture_snapshot_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture"
            fixture.mkdir()
            metadata = Path(temporary) / "verification-metadata.xml"
            metadata.write_text("metadata", encoding="utf-8")
            for entry in VERIFY.FIXTURE_ENTRIES:
                path = fixture / entry
                if entry == "src":
                    path.mkdir()
                    (path / "Main.java").write_text("class Main {}", encoding="utf-8")
                else:
                    path.write_text(entry, encoding="utf-8")
            (fixture / "src/link").symlink_to(fixture / "src/Main.java")
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.fixture_snapshot(fixture, metadata)


if __name__ == "__main__":
    unittest.main()
