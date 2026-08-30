from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "render-maven-pilot-starter.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "routecontract_render_maven_pilot_starter",
    SCRIPT,
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("cannot load render-maven-pilot-starter.py for fault-injection tests")
STARTER = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = STARTER
MODULE_SPEC.loader.exec_module(STARTER)
OUTPUT_NAMES = {
    "NEXT-STEPS.md",
    "assisted-pilot.json",
    "bundle-manifest.json",
    "pilot-spec.json",
    "routecontract-pilot.patch",
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class TargetFixture:
    def __init__(self, root: Path, *, existing_profiles: bool = False) -> None:
        self.root = root
        self.module = root / "integration-tests"
        self.root.mkdir()
        self.module.mkdir()
        (root / ".gitignore").write_text("**/target/\n", encoding="utf-8")
        (root / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>target-parent</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <packaging>pom</packaging>
  <modules><module>integration-tests</module></modules>
</project>
""",
            encoding="utf-8",
        )
        profiles = """
  <profiles>
    <profile>
      <id>existing-unrelated-profile</id>
    </profile>
  </profiles>
""" if existing_profiles else ""
        (self.module / "pom.xml").write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example</groupId>
    <artifactId>target-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
  </parent>
  <artifactId>integration-tests</artifactId>
{profiles}</project>
""",
            encoding="utf-8",
        )
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "RouteContract Test")
        self.git("config", "user.email", "routecontract-test@example.invalid")
        self.commit("initial target")

    def git(self, *arguments: str) -> bytes:
        result = run(["git", *arguments], self.root)
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    @property
    def head(self) -> str:
        return self.git("rev-parse", "HEAD").decode("ascii").strip()

    @property
    def pom_sha256(self) -> str:
        return sha256((self.module / "pom.xml").read_bytes())

    def config(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "projectRoot": os.fspath(self.root),
            "expectedTargetCommit": self.head,
            "expectedPomSha256": self.pom_sha256,
            "owningModule": "integration-tests",
            "reactorSelector": "integration-tests/pom.xml",
            "profileOffTest": (
                "com.example.orders.OrderQueryIntegrationTest"
                "#existingBusinessAssertionPasses"
            ),
            "profileOffTestShape": "single-non-parameterized",
            "pilotPackage": "com.example.orders",
            "pilotClass": "OrderQueryRouteContractTest",
            "pilotMethod": "capturesCandidate",
            "operationId": "orders.find-by-user-id",
            "reviewedMaxAttempts": 1,
            "reviewedMaxDataSources": 1,
            "dataSourceAliases": [
                {"observedName": "ds_1", "alias": "orders-shard-b"},
                {"observedName": "ds_0", "alias": "orders-shard-a"},
            ],
            "shardingSphereScope": "test",
            "javaVersion": "17",
            "mavenVersion": "3.9.14",
            "shardingSphereVersion": "5.5.3",
            "routeContractVersion": "0.1.2",
        }

    def refresh_binding(self, config: dict[str, object]) -> None:
        config["expectedTargetCommit"] = self.head
        config["expectedPomSha256"] = self.pom_sha256

    def status(self) -> bytes:
        return self.git("status", "--porcelain=v1", "-z", "--untracked-files=all")

    def byte_snapshot(self) -> dict[str, tuple[int, bytes]]:
        result: dict[str, tuple[int, bytes]] = {}
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root)
            if relative.parts and relative.parts[0] == ".git":
                continue
            metadata = os.lstat(path)
            if stat.S_ISREG(metadata.st_mode):
                result[relative.as_posix()] = (
                    stat.S_IMODE(metadata.st_mode),
                    path.read_bytes(),
                )
            elif stat.S_ISLNK(metadata.st_mode):
                result[relative.as_posix()] = (
                    stat.S_IMODE(metadata.st_mode),
                    os.readlink(path).encode("utf-8"),
                )
        return result


class MavenPilotStarterTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.scratch = Path(self.temporary.name).resolve()
        self.target = TargetFixture(self.scratch / "target")

    def write_config(
        self,
        config: dict[str, object] | None = None,
        *,
        name: str = "starter.json",
    ) -> Path:
        path = self.scratch / name
        value = self.target.config() if config is None else config
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def invoke(self, config: Path, output: Path) -> subprocess.CompletedProcess[bytes]:
        return run(
            [
                sys.executable,
                "-I",
                os.fspath(SCRIPT),
                "--config",
                os.fspath(config),
                "--output",
                os.fspath(output),
            ],
            ROOT,
        )

    def assert_rejected_without_target_change(
        self,
        config: Path,
        output: Path,
        message: str,
    ) -> None:
        before_bytes = self.target.byte_snapshot()
        before_status = self.target.status()
        result = self.invoke(config, output)
        self.assertEqual(2, result.returncode, result.stdout.decode())
        self.assertIn(message.encode("utf-8"), result.stderr)
        self.assertFalse(os.path.lexists(output))
        self.assertEqual(before_status, self.target.status())
        self.assertEqual(before_bytes, self.target.byte_snapshot())

    def test_renders_deterministic_review_bundle_without_touching_target(self) -> None:
        config_path = self.write_config()
        output = self.scratch / "review-bundle"
        before_bytes = self.target.byte_snapshot()
        before_status = self.target.status()

        result = self.invoke(config_path, output)

        self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertEqual(b"", result.stderr)
        expected_manifest_sha256 = sha256(
            (output / "bundle-manifest.json").read_bytes()
        )
        self.assertEqual(
            (
                "ROUTECONTRACT_MAVEN_PILOT_STARTER "
                f"targetCommit={self.target.head} "
                f"manifestSha256={expected_manifest_sha256} files=5 VERIFIED\n"
            ).encode("ascii"),
            result.stdout,
        )
        self.assertEqual(before_status, self.target.status())
        self.assertEqual(before_bytes, self.target.byte_snapshot())
        self.assertEqual(OUTPUT_NAMES, {path.name for path in output.iterdir()})
        self.assertEqual(0o700, stat.S_IMODE(os.lstat(output).st_mode))
        for path in output.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(0o600, stat.S_IMODE(os.lstat(path).st_mode))

        patch = (output / "routecontract-pilot.patch").read_text(encoding="utf-8")
        self.assertEqual(2, patch.count("diff --git "))
        self.assertIn("<id>routecontract-pilot</id>", patch)
        self.assertIn("<version>0.1.2</version>", patch)
        self.assertIn("<version>5.5.3</version>", patch)
        self.assertIn("<artifactId>junit-jupiter</artifactId>", patch)
        self.assertIn("<version>5.14.3</version>", patch)
        self.assertIn("<artifactId>maven-compiler-plugin</artifactId>", patch)
        self.assertIn("<id>default-testCompile</id>", patch)
        self.assertIn("<phase>test-compile</phase>", patch)
        self.assertIn("<goal>testCompile</goal>", patch)
        self.assertIn("<release>17</release>", patch)
        self.assertIn("<testRelease>17</testRelease>", patch)
        self.assertIn("<id>default-test</id>", patch)
        self.assertIn("<phase>test</phase>", patch)
        self.assertIn("<goal>test</goal>", patch)
        self.assertIn(
            "<reportsDirectory>${project.basedir}/target/surefire-reports</reportsDirectory>",
            patch,
        )
        self.assertIn(
            '<reportNameSuffix combine.self="override"></reportNameSuffix>',
            patch,
        )
        self.assertIn(
            "<promoteUserPropertiesToSystemProperties>false"
            "</promoteUserPropertiesToSystemProperties>",
            patch,
        )
        self.assertEqual(2, patch.count("<rerunFailingTestsCount>0</rerunFailingTestsCount>"))
        self.assertIn("ROUTECONTRACT_STARTER_REVIEW_REQUIRED", patch)
        self.assertNotIn(
            "diff --git a/integration-tests/src/routeContractPilot/resources/",
            patch,
        )
        check = run(
            ["git", "apply", "--check", "--whitespace=error-all", os.fspath(output / "routecontract-pilot.patch")],
            self.target.root,
        )
        self.assertEqual(0, check.returncode, check.stderr.decode())

        assisted = json.loads((output / "assisted-pilot.json").read_text())
        self.assertEqual(
            {
                "projectRoot",
                "owningModule",
                "reactorSelector",
                "profileOffTest",
                "pilotTest",
                "operationId",
            },
            set(assisted),
        )
        self.assertEqual(
            "com.example.orders.OrderQueryRouteContractTest#capturesCandidate",
            assisted["pilotTest"],
        )
        next_steps = (output / "NEXT-STEPS.md").read_text(encoding="utf-8")
        self.assertNotIn(os.fspath(self.target.root), next_steps)
        self.assertIn(
            "`assisted-pilot.json` and `pilot-spec.json` are host-local: their absolute",
            next_steps,
        )
        self.assertIn(
            "only `assisted-pilot.json` is runner input",
            next_steps,
        )
        self.assertIn(
            "Retain the renderer's out-of-band `manifestSha256` success field",
            next_steps,
        )
        self.assertIn(
            "integration-tests/target/routecontract/"
            "orders.find-by-user-id.candidate.json",
            next_steps,
        )
        self.assertIn(
            "integration-tests/target/surefire-reports/"
            "TEST-com.example.orders.OrderQueryIntegrationTest.xml",
            next_steps,
        )
        self.assertIn(
            "integration-tests/target/surefire-reports/"
            "TEST-com.example.orders.OrderQueryRouteContractTest.xml",
            next_steps,
        )
        self.assertIn(
            'config = {"owningModule":"integration-tests",'
            '"reactorSelector":"integration-tests/pom.xml",'
            '"profileOffTest":"com.example.orders.OrderQueryIntegrationTest'
            '#existingBusinessAssertionPasses",'
            '"pilotTest":"com.example.orders.OrderQueryRouteContractTest'
            '#capturesCandidate","operationId":"orders.find-by-user-id"}',
            next_steps,
        )
        self.assertIn(
            'config = {"projectRoot": os.fspath(root), **config}',
            next_steps,
        )
        self.assertEqual(2, next_steps.count("--expected-outcome matched"))
        self.assertEqual(
            2,
            next_steps.count(
                'bundle_root="/absolute/path/to/'
                'the-new-output-directory-used-with---output"'
            ),
        )
        self.assertNotIn("run the same config", next_steps)
        ci_marker = '   python3 -I - "${target_root}" "${ci_config}" <<\'PY\'\n'
        ci_start = next_steps.index(ci_marker) + len(ci_marker)
        ci_program = textwrap.dedent(
            next_steps[ci_start : next_steps.index("\n   PY\n", ci_start)]
        )
        ci_config = self.scratch / "ci-assisted-pilot.json"
        ci_result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-",
                os.fspath(self.target.root),
                os.fspath(ci_config),
            ],
            input=ci_program.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, ci_result.returncode, ci_result.stderr.decode())
        self.assertEqual(0o600, stat.S_IMODE(os.lstat(ci_config).st_mode))
        self.assertEqual(assisted, json.loads(ci_config.read_text(encoding="utf-8")))
        normalized = json.loads((output / "pilot-spec.json").read_text())
        self.assertEqual(
            ["ds_0", "ds_1"],
            [item["observedName"] for item in normalized["dataSourceAliases"]],
        )
        manifest = json.loads((output / "bundle-manifest.json").read_text())
        self.assertTrue(manifest["reviewOnly"])
        self.assertFalse(manifest["baselineGenerated"])
        self.assertEqual(self.target.head, manifest["target"]["commit"])
        self.assertEqual(self.target.pom_sha256, manifest["target"]["owningPomSha256"])
        for record in manifest["generatedFiles"]:
            payload = (output / record["path"]).read_bytes()
            self.assertEqual(len(payload), record["bytes"])
            self.assertEqual(sha256(payload), record["sha256"])

        approved = (
            self.target.module
            / "src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
        )
        candidate = self.target.module / "target/routecontract/orders.find-by-user-id.candidate.json"
        pilot = (
            self.target.module
            / "src/routeContractPilot/java/com/example/orders/OrderQueryRouteContractTest.java"
        )
        self.assertFalse(os.path.lexists(approved))
        self.assertFalse(os.path.lexists(candidate))
        self.assertFalse(os.path.lexists(pilot))

    def test_applied_patch_generated_java_compiles_on_release_17(self) -> None:
        config = self.write_config()
        output = self.scratch / "compile-bundle"
        rendered = self.invoke(config, output)
        self.assertEqual(0, rendered.returncode, rendered.stderr.decode())
        applied = run(
            ["git", "apply", os.fspath(output / "routecontract-pilot.patch")],
            self.target.root,
        )
        self.assertEqual(0, applied.returncode, applied.stderr.decode())

        verifier = (ROOT / "scripts/verify-external-maven-integration.sh").read_text(
            encoding="utf-8"
        )
        verifier_marker = 'python3 -I - "$ROUTECONTRACT_OWNING_POM" <<\'PY\'\n'
        verifier_start = verifier.index(verifier_marker) + len(verifier_marker)
        verifier_parser = verifier[verifier_start : verifier.index("\nPY\n", verifier_start)]
        source_pom = self.target.module / "pom.xml"
        verifier_result = run(
            [sys.executable, "-I", "-c", verifier_parser, os.fspath(source_pom)],
            self.scratch,
        )
        self.assertEqual(0, verifier_result.returncode, verifier_result.stderr.decode())
        tampered_pom = self.scratch / "tampered-source-pom.xml"
        tampered_pom.write_text(
            source_pom.read_text(encoding="utf-8").replace(
                "<promoteUserPropertiesToSystemProperties>false",
                "<promoteUserPropertiesToSystemProperties>true",
            ),
            encoding="utf-8",
        )
        tampered_result = run(
            [sys.executable, "-I", "-c", verifier_parser, os.fspath(tampered_pom)],
            self.scratch,
        )
        self.assertNotEqual(0, tampered_result.returncode)
        self.assertIn(b"promoteUserPropertiesToSystemProperties", tampered_result.stderr)

        duplicate_property_pom = self.scratch / "duplicate-property-source-pom.xml"
        duplicate_property_pom.write_text(
            source_pom.read_text(encoding="utf-8").replace(
                "<routecontract.projectDir>${project.basedir}"
                "</routecontract.projectDir>",
                "<routecontract.projectDir>${project.basedir}"
                "</routecontract.projectDir>"
                "<routecontract.projectDir>/tmp/unsafe"
                "</routecontract.projectDir>",
                1,
            ),
            encoding="utf-8",
        )
        duplicate_property_result = run(
            [
                sys.executable,
                "-I",
                "-c",
                verifier_parser,
                os.fspath(duplicate_property_pom),
            ],
            self.scratch,
        )
        self.assertNotEqual(0, duplicate_property_result.returncode)
        self.assertIn(b"system properties child inventory changed", duplicate_property_result.stderr)

        duplicate_toggle_pom = self.scratch / "duplicate-toggle-source-pom.xml"
        duplicate_toggle_pom.write_text(
            source_pom.read_text(encoding="utf-8").replace(
                "<promoteUserPropertiesToSystemProperties>false"
                "</promoteUserPropertiesToSystemProperties>",
                "<promoteUserPropertiesToSystemProperties>false"
                "</promoteUserPropertiesToSystemProperties>"
                "<promoteUserPropertiesToSystemProperties>true"
                "</promoteUserPropertiesToSystemProperties>",
                1,
            ),
            encoding="utf-8",
        )
        duplicate_toggle_result = run(
            [
                sys.executable,
                "-I",
                "-c",
                verifier_parser,
                os.fspath(duplicate_toggle_pom),
            ],
            self.scratch,
        )
        self.assertNotEqual(0, duplicate_toggle_result.returncode)
        self.assertIn(b"configuration child inventory changed", duplicate_toggle_result.stderr)

        namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
        pom_root = ET.parse(self.target.module / "pom.xml").getroot()
        surefire_plugins = [
            plugin
            for plugin in pom_root.findall(
                "m:profiles/m:profile/m:build/m:plugins/m:plugin",
                namespace,
            )
            if plugin.findtext("m:artifactId", default="", namespaces=namespace)
            == "maven-surefire-plugin"
        ]
        self.assertEqual(1, len(surefire_plugins))
        direct_configuration = surefire_plugins[0].find("m:configuration", namespace)
        execution_configuration = surefire_plugins[0].find(
            "m:executions/m:execution/m:configuration",
            namespace,
        )
        self.assertIsNotNone(
            direct_configuration,
            "the pinned assisted verifier requires plugin-level Surefire properties",
        )
        self.assertIsNotNone(
            execution_configuration,
            "execution-level target configuration must not override the evidence boundary",
        )
        for configuration in (direct_configuration, execution_configuration):
            if configuration is None:
                continue
            self.assertNotIn("combine.self", configuration.attrib)
            suffix = configuration.find("m:reportNameSuffix", namespace)
            self.assertIsNotNone(suffix)
            if suffix is not None:
                self.assertEqual("override", suffix.attrib.get("combine.self"))
            properties = configuration.find("m:systemPropertyVariables", namespace)
            self.assertIsNotNone(properties)
            self.assertEqual(
                "false",
                configuration.findtext(
                    "m:promoteUserPropertiesToSystemProperties",
                    default="",
                    namespaces=namespace,
                ),
            )
            self.assertEqual(
                "${project.basedir}",
                properties.findtext(
                    "m:routecontract.projectDir",
                    default="",
                    namespaces=namespace,
                ) if properties is not None else "",
            )

        generated = (
            self.target.module
            / "src/routeContractPilot/java/com/example/orders/OrderQueryRouteContractTest.java"
        )
        stub_root = self.scratch / "java-stubs"
        stubs = {
            "org/junit/jupiter/api/Test.java": """
package org.junit.jupiter.api;
public @interface Test {}
""",
            "org/junit/jupiter/api/Assertions.java": """
package org.junit.jupiter.api;
public final class Assertions {
    public static void assertEquals(Object expected, Object actual) {}
    public static void assertEquals(Object expected, Object actual, String message) {}
    public static <T> T fail(String message) { throw new AssertionError(message); }
}
""",
            "io/github/ym0506/routecontract/RouteSnapshot.java": """
package io.github.ym0506.routecontract;
public final class RouteSnapshot {}
""",
            "io/github/ym0506/routecontract/RouteContract.java": """
package io.github.ym0506.routecontract;
public final class RouteContract {
    @FunctionalInterface public interface Action { void run() throws Exception; }
    public static RouteSnapshot capture(String operationId, Action action) {
        return new RouteSnapshot();
    }
}
""",
            "io/github/ym0506/routecontract/RouteAssertions.java": """
package io.github.ym0506.routecontract;
public final class RouteAssertions {
    public static RouteAssertions assertThat(RouteSnapshot snapshot) {
        return new RouteAssertions();
    }
    public RouteAssertions hasCompleteCapture() { return this; }
    public RouteAssertions hasNoReportedExecutionFailures() { return this; }
    public RouteAssertions hasAtMostObservedPhysicalAttempts(int value) { return this; }
    public RouteAssertions hasAtMostDistinctObservedDataSourceNames(int value) { return this; }
}
""",
            "io/github/ym0506/routecontract/manifest/DataSourceAliases.java": """
package io.github.ym0506.routecontract.manifest;
import java.util.Map;
public final class DataSourceAliases {
    public static DataSourceAliases of(Map<String, String> values) {
        return new DataSourceAliases();
    }
}
""",
            "io/github/ym0506/routecontract/manifest/ManifestPolicy.java": """
package io.github.ym0506.routecontract.manifest;
public final class ManifestPolicy {
    public static ManifestPolicy strict(int attempts, int dataSources) {
        return new ManifestPolicy();
    }
}
""",
            "io/github/ym0506/routecontract/manifest/ObservedExecutionManifest.java": """
package io.github.ym0506.routecontract.manifest;
import io.github.ym0506.routecontract.RouteSnapshot;
public final class ObservedExecutionManifest {
    public static ObservedExecutionManifest from(
            RouteSnapshot snapshot, DataSourceAliases aliases, ManifestPolicy policy) {
        return new ObservedExecutionManifest();
    }
}
""",
            "io/github/ym0506/routecontract/manifest/ManifestStore.java": """
package io.github.ym0506.routecontract.manifest;
import java.nio.file.Path;
public final class ManifestStore {
    public void writeCandidate(Path approved, Path candidate, ObservedExecutionManifest value) {}
    public Object read(Path approved) { return new Object(); }
}
""",
            "io/github/ym0506/routecontract/manifest/ManifestVerifier.java": """
package io.github.ym0506.routecontract.manifest;
public final class ManifestVerifier {
    public Object verify(Object approved, ObservedExecutionManifest candidate) {
        return new Object();
    }
}
""",
            "io/github/ym0506/routecontract/manifest/ManifestAssertions.java": """
package io.github.ym0506.routecontract.manifest;
public final class ManifestAssertions {
    public static void assertMatched(Object result) {}
}
""",
        }
        sources = [generated]
        for relative, source in stubs.items():
            path = stub_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source.strip() + "\n", encoding="utf-8")
            sources.append(path)
        javac = shutil.which("javac")
        self.assertIsNotNone(javac, "Java 17 javac is required for the starter contract test")
        classes = self.scratch / "compiled-classes"
        classes.mkdir()
        compiled = run(
            [
                os.path.realpath(javac or "javac"),
                "--release",
                "17",
                "-d",
                os.fspath(classes),
                *[os.fspath(path) for path in sources],
            ],
            self.scratch,
        )
        self.assertEqual(0, compiled.returncode, compiled.stderr.decode())

    def test_output_is_byte_deterministic_for_same_target_and_config(self) -> None:
        config = self.write_config()
        first = self.scratch / "first-bundle"
        second = self.scratch / "second-bundle"
        self.assertEqual(0, self.invoke(config, first).returncode)
        self.assertEqual(0, self.invoke(config, second).returncode)
        self.assertEqual(
            {path.name: path.read_bytes() for path in first.iterdir()},
            {path.name: path.read_bytes() for path in second.iterdir()},
        )

    def test_inserts_into_one_existing_profiles_element(self) -> None:
        second_target = TargetFixture(self.scratch / "target-with-profiles", existing_profiles=True)
        self.target = second_target
        config = self.write_config(name="existing-profiles.json")
        output = self.scratch / "profiles-bundle"
        result = self.invoke(config, output)
        self.assertEqual(0, result.returncode, result.stderr.decode())
        patch = (output / "routecontract-pilot.patch").read_text(encoding="utf-8")
        self.assertEqual(1, patch.count("+      <id>routecontract-pilot</id>"))
        self.assertNotIn("+  <profiles>", patch)
        check = run(["git", "apply", "--check", os.fspath(output / "routecontract-pilot.patch")], self.target.root)
        self.assertEqual(0, check.returncode, check.stderr.decode())

    def test_rejects_duplicate_and_unknown_json_keys(self) -> None:
        valid = self.target.config()
        duplicate = self.scratch / "duplicate.json"
        payload = json.dumps(valid, ensure_ascii=False, indent=2)
        duplicate.write_text(
            payload.replace('"schemaVersion": 1,', '"schemaVersion": 1,\n  "schemaVersion": 1,'),
            encoding="utf-8",
        )
        self.assert_rejected_without_target_change(
            duplicate,
            self.scratch / "duplicate-output",
            "duplicate key",
        )

        forged = self.scratch / "forged-key.json"
        forged.write_text(
            payload.replace(
                '"schemaVersion": 1,',
                '"schemaVersion": 1,\n  "unexpected\\nFORGED VERIFIED": 1,',
            ),
            encoding="utf-8",
        )
        forged_result = self.invoke(forged, self.scratch / "forged-output")
        self.assertNotEqual(0, forged_result.returncode)
        self.assertNotIn(b"\nFORGED VERIFIED", forged_result.stderr)
        self.assertNotIn(b"Traceback", forged_result.stderr)

        unknown_value = dict(valid)
        unknown_value["unexpected"] = "value"
        unknown = self.write_config(unknown_value, name="unknown.json")
        self.assert_rejected_without_target_change(
            unknown,
            self.scratch / "unknown-output",
            "config keys must match the schema exactly",
        )

        surrogate_value = dict(valid)
        surrogate_value["projectRoot"] = "\ud800"
        surrogate = self.scratch / "surrogate.json"
        surrogate.write_bytes(json.dumps(surrogate_value).encode("utf-8"))
        surrogate_result = self.invoke(
            surrogate,
            self.scratch / "surrogate-output",
        )
        self.assertNotEqual(0, surrogate_result.returncode)
        self.assertNotIn(b"Traceback", surrogate_result.stderr)

        non_json_number = self.scratch / "non-json-number.json"
        non_json_number.write_text(
            json.dumps(valid, ensure_ascii=False, indent=2).replace(
                '"reviewedMaxAttempts": 1',
                '"reviewedMaxAttempts": NaN',
            ),
            encoding="utf-8",
        )
        self.assert_rejected_without_target_change(
            non_json_number,
            self.scratch / "non-json-number-output",
            "non-JSON numeric constant: NaN",
        )

    def test_rejects_abbreviated_and_duplicate_cli_options(self) -> None:
        config = self.write_config()
        output = self.scratch / "cli-output"
        before_bytes = self.target.byte_snapshot()
        before_status = self.target.status()

        abbreviated = run(
            [
                sys.executable,
                "-I",
                os.fspath(SCRIPT),
                "--conf",
                os.fspath(config),
                "--output",
                os.fspath(output),
            ],
            ROOT,
        )
        self.assertEqual(2, abbreviated.returncode)
        self.assertIn(b"unrecognized arguments: --conf", abbreviated.stderr)

        duplicate = run(
            [
                sys.executable,
                "-I",
                os.fspath(SCRIPT),
                "--config",
                os.fspath(config),
                "--config",
                os.fspath(config),
                "--output",
                os.fspath(output),
            ],
            ROOT,
        )
        self.assertEqual(2, duplicate.returncode)
        self.assertIn(b"--config may be supplied only once", duplicate.stderr)
        self.assertFalse(os.path.lexists(output))
        self.assertEqual(before_status, self.target.status())
        self.assertEqual(before_bytes, self.target.byte_snapshot())

        forged_output = self.scratch / "output\nFORGED VERIFIED"
        forged_output_result = self.invoke(config, forged_output)
        self.assertNotEqual(0, forged_output_result.returncode)
        self.assertNotIn(b"\nFORGED VERIFIED", forged_output_result.stdout)
        self.assertNotIn(b"Traceback", forged_output_result.stderr)

    def test_fails_closed_on_output_byte_or_inventory_tampering(self) -> None:
        config = self.write_config()
        prepared = STARTER._prepare(config)
        original_write = STARTER._write_one

        tampered_once = False

        def tamper_bytes(
            directory_fd: int,
            name: str,
            payload: bytes,
        ) -> os.stat_result:
            nonlocal tampered_once
            created = original_write(directory_fd, name, payload)
            if not tampered_once:
                tampered_once = True
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_TRUNC,
                    dir_fd=directory_fd,
                )
                try:
                    os.write(descriptor, b"tampered\n")
                finally:
                    os.close(descriptor)
            return created

        with mock.patch.object(STARTER, "_write_one", side_effect=tamper_bytes):
            with self.assertRaisesRegex(STARTER.StarterError, "output file bytes changed"):
                STARTER._write_bundle(prepared, os.fspath(self.scratch / "tampered"))

        injected_once = False

        def inject_extra(
            directory_fd: int,
            name: str,
            payload: bytes,
        ) -> os.stat_result:
            nonlocal injected_once
            created = original_write(directory_fd, name, payload)
            if not injected_once:
                injected_once = True
                descriptor = os.open(
                    "unexpected",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                os.close(descriptor)
            return created

        with mock.patch.object(STARTER, "_write_one", side_effect=inject_extra):
            with self.assertRaisesRegex(STARTER.StarterError, "output inventory changed"):
                STARTER._write_bundle(prepared, os.fspath(self.scratch / "extra-file"))

        self.assertEqual(b"", self.target.status())

    def test_partial_output_file_is_removed_after_write_failure(self) -> None:
        directory = self.scratch / "partial-output"
        directory.mkdir(mode=0o700)
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        writes = 0

        def fail_after_partial_write(descriptor: int, payload: object) -> int:
            nonlocal writes
            writes += 1
            if writes == 1:
                return 1
            raise OSError("injected write failure")

        try:
            with mock.patch.object(STARTER.os, "write", side_effect=fail_after_partial_write):
                with self.assertRaisesRegex(
                    STARTER.StarterError,
                    "cannot complete output file",
                ):
                    STARTER._write_one(directory_fd, "NEXT-STEPS.md", b"payload")
        finally:
            os.close(directory_fd)
        self.assertEqual([], list(directory.iterdir()))

    def test_close_failure_removes_unregistered_output_file(self) -> None:
        directory = self.scratch / "close-failure"
        directory.mkdir(mode=0o700)
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        original_close = STARTER.os.close

        def close_file_then_fail(descriptor: int) -> None:
            original_close(descriptor)
            raise OSError("injected close failure")

        try:
            with mock.patch.object(
                STARTER.os,
                "close",
                side_effect=close_file_then_fail,
            ):
                with self.assertRaisesRegex(
                    STARTER.StarterError,
                    "cannot close output file",
                ):
                    STARTER._write_one(directory_fd, "NEXT-STEPS.md", b"payload")
        finally:
            original_close(directory_fd)
        self.assertEqual([], list(directory.iterdir()))

    def test_preidentity_file_and_directory_failures_leave_no_bundle(self) -> None:
        directory = self.scratch / "preidentity-file"
        directory.mkdir(mode=0o700)
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            with mock.patch.object(
                STARTER.os,
                "fstat",
                side_effect=OSError("injected initial fstat failure"),
            ):
                with self.assertRaisesRegex(
                    STARTER.StarterError,
                    "cannot complete output file",
                ):
                    STARTER._write_one(directory_fd, "NEXT-STEPS.md", b"payload")
        finally:
            os.close(directory_fd)
        self.assertEqual([], list(directory.iterdir()))

        config = self.write_config()
        prepared = STARTER._prepare(config)
        output = self.scratch / "preidentity-directory"
        original_open = STARTER.os.open

        def fail_output_root_open(path: object, *args: object, **kwargs: object) -> int:
            if path == output.name and kwargs.get("dir_fd") is not None:
                raise OSError("injected output-root open failure")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(STARTER.os, "open", side_effect=fail_output_root_open):
            with self.assertRaisesRegex(
                STARTER.StarterError,
                "output root could not be initialized",
            ):
                STARTER._write_bundle(prepared, os.fspath(output))
        self.assertFalse(os.path.lexists(output))

    def test_fails_closed_if_named_output_root_is_swapped(self) -> None:
        config = self.write_config()
        prepared = STARTER._prepare(config)
        output = self.scratch / "swapped-root"
        moved = self.scratch / "original-root"
        original_listdir = os.listdir
        swapped = False

        def swap_after_inventory(path: object) -> list[str]:
            nonlocal swapped
            names = original_listdir(path)
            if isinstance(path, int) and not swapped:
                swapped = True
                output.rename(moved)
                output.mkdir(mode=0o700)
            return names

        with mock.patch.object(STARTER.os, "listdir", side_effect=swap_after_inventory):
            with self.assertRaisesRegex(STARTER.StarterError, "output root identity"):
                STARTER._write_bundle(prepared, os.fspath(output))

        self.assertTrue(moved.is_dir())
        self.assertTrue(output.is_dir())
        self.assertEqual(b"", self.target.status())

    def test_fails_closed_if_ignored_baseline_appears_during_render(self) -> None:
        approved = (
            self.target.module
            / "src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
        )
        with (self.target.root / ".gitignore").open("a", encoding="utf-8") as stream:
            stream.write(
                "integration-tests/src/routeContractPilot/resources/route-contracts/"
                "orders.find-by-user-id.json\n"
            )
        self.target.commit("ignore baseline for concurrent-appearance test")
        config = self.write_config(self.target.config(), name="ignored-baseline.json")
        prepared = STARTER._prepare(config)
        original_write = STARTER._write_one
        injected_once = False

        def inject_baseline(
            directory_fd: int,
            name: str,
            payload: bytes,
        ) -> os.stat_result:
            nonlocal injected_once
            created = original_write(directory_fd, name, payload)
            if not injected_once:
                injected_once = True
                approved.parent.mkdir(parents=True)
                approved.write_bytes(b"not approved by the starter\n")
            return created

        with mock.patch.object(STARTER, "_write_one", side_effect=inject_baseline):
            with self.assertRaisesRegex(STARTER.StarterError, "approved baseline must start absent"):
                STARTER._write_bundle(
                    prepared,
                    os.fspath(self.scratch / "baseline-appeared"),
                )

        self.assertEqual(b"", self.target.status())
        self.assertEqual(b"not approved by the starter\n", approved.read_bytes())

    def test_rejects_every_unsupported_boundary_version_and_boolean_schema(self) -> None:
        cases: list[tuple[str, object, str]] = [
            ("javaVersion", "21", "javaVersion must be exactly 17"),
            ("mavenVersion", "3.9.13", "mavenVersion must be exactly 3.9.14"),
            (
                "shardingSphereVersion",
                "5.5.2",
                "shardingSphereVersion must be exactly 5.5.3",
            ),
            (
                "routeContractVersion",
                "0.1.1",
                "routeContractVersion must be exactly 0.1.2",
            ),
            ("schemaVersion", True, "schemaVersion must be exactly 1"),
        ]
        for index, (key, value, message) in enumerate(cases):
            with self.subTest(key=key):
                config = self.target.config()
                config[key] = value
                path = self.write_config(config, name=f"boundary-{index}.json")
                self.assert_rejected_without_target_change(
                    path,
                    self.scratch / f"boundary-output-{index}",
                    message,
                )

    def test_rejects_bad_commit_pom_binding_and_dirty_target(self) -> None:
        config = self.target.config()
        config["expectedTargetCommit"] = "f" * 40
        path = self.write_config(config, name="bad-head.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "bad-head-output",
            "target HEAD differs",
        )

        config = self.target.config()
        config["expectedPomSha256"] = "f" * 64
        path = self.write_config(config, name="bad-pom.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "bad-pom-output",
            "owning POM differs",
        )

        dirty_config = self.write_config(name="dirty.json")
        (self.target.root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        before = self.target.byte_snapshot()
        result = self.invoke(dirty_config, self.scratch / "dirty-output")
        self.assertEqual(2, result.returncode)
        self.assertIn(b"target worktree must be clean", result.stderr)
        self.assertFalse((self.scratch / "dirty-output").exists())
        self.assertEqual(before, self.target.byte_snapshot())

    def test_git_inspection_output_is_bounded(self) -> None:
        with mock.patch.object(STARTER, "MAX_GIT_OUTPUT_BYTES", 1):
            with self.assertRaisesRegex(
                STARTER.StarterError,
                "git inspection output exceeded its size limit",
            ):
                STARTER._run_git(self.target.root, ["rev-parse", "HEAD"])

    def test_rejects_hidden_owning_pom_worktree_bytes(self) -> None:
        for index, flag in enumerate(("--assume-unchanged", "--skip-worktree")):
            with self.subTest(flag=flag):
                self.target = TargetFixture(self.scratch / f"hidden-pom-{index}")
                pom = self.target.module / "pom.xml"
                pom.write_text(
                    pom.read_text(encoding="utf-8").replace(
                        "<artifactId>integration-tests</artifactId>",
                        "<artifactId>hidden-worktree-edit</artifactId>",
                    ),
                    encoding="utf-8",
                )
                self.target.git(
                    "update-index",
                    flag,
                    "integration-tests/pom.xml",
                )
                self.assertEqual(b"", self.target.status())
                config = self.target.config()
                config["expectedPomSha256"] = sha256(pom.read_bytes())
                path = self.write_config(config, name=f"hidden-pom-{index}.json")
                self.assert_rejected_without_target_change(
                    path,
                    self.scratch / f"hidden-pom-output-{index}",
                    "target index must not contain assume-unchanged",
                )

    def test_rejects_existing_or_symlinked_output_and_output_inside_target(self) -> None:
        config = self.write_config()
        existing = self.scratch / "existing-output"
        existing.mkdir()
        result = self.invoke(config, existing)
        self.assertEqual(2, result.returncode)
        self.assertIn(b"output root must be new and absent", result.stderr)

        symlink = self.scratch / "symlink-output"
        symlink.symlink_to(existing, target_is_directory=True)
        result = self.invoke(config, symlink)
        self.assertEqual(2, result.returncode)
        self.assertIn(b"output root must be new and absent", result.stderr)

        inside = self.target.root / "bundle"
        result = self.invoke(config, inside)
        self.assertEqual(2, result.returncode)
        self.assertIn(b"outside every target Git worktree", result.stderr)
        self.assertFalse(inside.exists())

    def test_rejects_group_or_other_writable_output_parent(self) -> None:
        config = self.write_config()
        insecure_parent = self.scratch / "insecure-parent"
        insecure_parent.mkdir(mode=0o700)
        os.chmod(insecure_parent, 0o777)
        try:
            output = insecure_parent / "bundle"
            result = self.invoke(config, output)
            self.assertEqual(2, result.returncode, result.stdout.decode())
            self.assertIn(
                b"owned by the current user and not group/other writable",
                result.stderr,
            )
            self.assertFalse(os.path.lexists(output))
            self.assertEqual(b"", self.target.status())
        finally:
            os.chmod(insecure_parent, 0o700)

    @unittest.skipUnless(sys.platform == "darwin", "macOS extended ACL probe")
    def test_rejects_macos_extended_acl_on_output_parent(self) -> None:
        config = self.write_config()
        acl_parent = self.scratch / "acl-parent"
        acl_parent.mkdir(mode=0o700)
        add_acl = run(
            [
                "/bin/chmod",
                "+a",
                "everyone allow list,search,file_inherit,directory_inherit",
                os.fspath(acl_parent),
            ]
        )
        self.assertEqual(0, add_acl.returncode, add_acl.stderr.decode())
        try:
            output = acl_parent / "bundle"
            result = self.invoke(config, output)
            self.assertEqual(2, result.returncode, result.stdout.decode())
            self.assertIn(
                b"output parent must not carry an extended ACL",
                result.stderr,
            )
            self.assertFalse(os.path.lexists(output))
            self.assertEqual(b"", self.target.status())
        finally:
            clear_acl = run(["/bin/chmod", "-N", os.fspath(acl_parent)])
            self.assertEqual(0, clear_acl.returncode, clear_acl.stderr.decode())

    def test_directory_close_errors_do_not_skip_other_closes_or_invalidate_bundle(self) -> None:
        config = self.write_config()
        prepared = STARTER._prepare(config)
        output = self.scratch / "directory-close-errors"
        original_close = STARTER.os.close
        injected = 0

        def close_directory_then_fail(descriptor: int) -> None:
            nonlocal injected
            metadata = os.fstat(descriptor)
            original_close(descriptor)
            if stat.S_ISDIR(metadata.st_mode) and injected < 2:
                injected += 1
                raise OSError("injected directory close failure")

        with mock.patch.object(
            STARTER.os,
            "close",
            side_effect=close_directory_then_fail,
        ):
            result = STARTER._write_bundle(prepared, os.fspath(output))

        self.assertEqual(output, result)
        self.assertEqual(2, injected)
        self.assertEqual(OUTPUT_NAMES, {path.name for path in output.iterdir()})
        self.assertEqual(b"", self.target.status())

    def test_rejects_output_inside_any_linked_worktree_or_git_admin_area(self) -> None:
        primary = self.target
        linked_root = self.scratch / "linked-target"
        primary.git(
            "worktree",
            "add",
            "-q",
            "-b",
            "linked-review-target",
            os.fspath(linked_root),
        )
        linked = TargetFixture.__new__(TargetFixture)
        linked.root = linked_root
        linked.module = linked_root / "integration-tests"
        self.target = linked
        config = self.write_config(linked.config(), name="linked-target.json")
        common_git = Path(
            os.fsdecode(
                linked.git(
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                )
            ).strip()
        ).resolve(strict=True)
        before_refs = primary.git("show-ref")

        candidates = (
            primary.root / "routecontract-review-bundle",
            common_git / "refs" / "routecontract-review-bundle",
        )
        for output in candidates:
            with self.subTest(output=os.fspath(output)):
                result = self.invoke(config, output)
                self.assertEqual(2, result.returncode, result.stdout.decode())
                self.assertIn(
                    b"outside every target Git worktree and administration directory",
                    result.stderr,
                )
                self.assertFalse(os.path.lexists(output))
                self.assertEqual(b"", linked.status())
                self.assertEqual(before_refs, primary.git("show-ref"))

    def test_rejects_config_project_module_and_output_parent_symlinks(self) -> None:
        config = self.write_config()
        config_link = self.scratch / "config-link.json"
        config_link.symlink_to(config)
        self.assert_rejected_without_target_change(
            config_link,
            self.scratch / "config-link-output",
            "config must use its canonical non-symlink path",
        )

        root_link = self.scratch / "target-link"
        root_link.symlink_to(self.target.root, target_is_directory=True)
        value = self.target.config()
        value["projectRoot"] = os.fspath(root_link)
        root_config = self.write_config(value, name="root-link.json")
        self.assert_rejected_without_target_change(
            root_config,
            self.scratch / "root-link-output",
            "projectRoot must be a canonical non-symlink directory",
        )

        real_parent = self.scratch / "real-parent"
        real_parent.mkdir()
        parent_link = self.scratch / "parent-link"
        parent_link.symlink_to(real_parent, target_is_directory=True)
        result = self.invoke(config, parent_link / "bundle")
        self.assertEqual(2, result.returncode)
        self.assertIn(b"output parent must be an existing canonical", result.stderr)

        module_real = self.target.root / "module-real"
        module_real.mkdir()
        (module_real / "pom.xml").write_text(
            (self.target.module / "pom.xml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        module_link = self.target.root / "module-link"
        module_link.symlink_to(module_real, target_is_directory=True)
        self.target.commit("add module symlink")
        value = self.target.config()
        value["owningModule"] = "module-link"
        value["reactorSelector"] = "module-link/pom.xml"
        value["expectedTargetCommit"] = self.target.head
        value["expectedPomSha256"] = sha256((module_real / "pom.xml").read_bytes())
        module_config = self.write_config(value, name="module-link.json")
        self.assert_rejected_without_target_change(
            module_config,
            self.scratch / "module-link-output",
            "owningModule must not traverse a symlink",
        )

    def test_rejects_path_traversal_unsafe_identifiers_aliases_and_budgets(self) -> None:
        cases: list[tuple[str, object, str]] = [
            ("owningModule", "../outside", "owningModule contains an unsafe"),
            ("reactorSelector", "pom.xml", "reactorSelector must equal"),
            ("pilotPackage", "com.example.class", "safe Java package"),
            ("pilotClass", "Bad-Class", "safe Java identifier"),
            ("pilotMethod", "class", "safe Java identifier"),
            ("pilotMethod", "_", "safe Java identifier"),
            ("operationId", "../secret", "safe manifest filename stem"),
            ("reviewedMaxAttempts", 0, "must be an integer"),
            ("reviewedMaxDataSources", 3, "cannot exceed the explicit alias universe"),
            ("shardingSphereScope", "provided", "must be compile, runtime, or test"),
            (
                "profileOffTestShape",
                "parameterized",
                "must be exactly single-non-parameterized",
            ),
        ]
        for index, (key, value, message) in enumerate(cases):
            with self.subTest(key=key):
                config = self.target.config()
                config[key] = value
                path = self.write_config(config, name=f"unsafe-{index}.json")
                self.assert_rejected_without_target_change(
                    path,
                    self.scratch / f"unsafe-output-{index}",
                    message,
                )

        collision = self.target.config()
        collision["dataSourceAliases"] = [
            {"observedName": "ds_0", "alias": "same"},
            {"observedName": "ds_1", "alias": "same"},
        ]
        path = self.write_config(collision, name="collision.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "collision-output",
            "alias collision",
        )

    def test_rejects_existing_pilot_candidate_or_baseline_even_when_ignored(self) -> None:
        cases = (
            (
                "src/routeContractPilot/java/com/example/orders/OrderQueryRouteContractTest.java",
                "pilot source must start absent",
            ),
            (
                "target/routecontract/orders.find-by-user-id.candidate.json",
                "candidate must start absent",
            ),
            (
                "src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json",
                "approved baseline must start absent",
            ),
        )
        for index, (relative, message) in enumerate(cases):
            with self.subTest(relative=relative):
                fixture = TargetFixture(self.scratch / f"existing-target-{index}")
                self.target = fixture
                with (fixture.root / ".gitignore").open("a", encoding="utf-8") as stream:
                    stream.write("integration-tests/" + relative + "\n")
                fixture.commit("ignore generated evidence for rejection test")
                existing = fixture.module / relative.removeprefix("integration-tests/")
                if relative.startswith("target/") or relative.startswith("src/"):
                    existing = fixture.module / relative
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_text("must remain\n", encoding="utf-8")
                self.assertEqual(b"", fixture.status())
                config = self.write_config(fixture.config(), name=f"existing-{index}.json")
                before = fixture.byte_snapshot()
                result = self.invoke(config, self.scratch / f"existing-output-{index}")
                self.assertEqual(2, result.returncode)
                self.assertIn(message.encode(), result.stderr)
                self.assertEqual(before, fixture.byte_snapshot())

    def test_rejects_ambiguous_pom_and_maven_execution_customization(self) -> None:
        pom = self.target.module / "pom.xml"
        text = pom.read_text(encoding="utf-8").replace(
            "  <artifactId>integration-tests</artifactId>",
            "  <artifactId>integration-tests</artifactId>\n  <!-- routecontract-pilot -->",
        )
        pom.write_text(text, encoding="utf-8")
        self.target.commit("add ambiguous pilot marker")
        config = self.target.config()
        path = self.write_config(config, name="pilot-marker.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "pilot-marker-output",
            "already contains a RouteContract pilot marker",
        )

        second = TargetFixture(self.scratch / "maven-customized")
        self.target = second
        dot_maven = second.root / ".mvn"
        dot_maven.mkdir()
        (dot_maven / "maven.config").write_text("-Dcustom=true\n", encoding="utf-8")
        second.commit("add Maven customization")
        path = self.write_config(second.config(), name="maven-customized.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "maven-customized-output",
            "outside the isolated Maven starter boundary",
        )

    def test_rejects_custom_profile_off_report_layout(self) -> None:
        cases = (
            (
                "reactor-build-directory",
                "reactor",
                "  <build><directory>custom-target</directory></build>\n",
                "custom build directory",
            ),
            (
                "owning-reports-directory",
                "owning",
                """  <build>
    <plugins><plugin>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration><reportsDirectory>custom-reports</reportsDirectory></configuration>
    </plugin></plugins>
  </build>
""",
                "custom Surefire reportsDirectory",
            ),
            (
                "owning-report-suffix",
                "owning",
                """  <build>
    <plugins><plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration><reportNameSuffix>pilot</reportNameSuffix></configuration>
    </plugin></plugins>
  </build>
""",
                "custom Surefire reportNameSuffix",
            ),
            (
                "owning-disable-xml",
                "owning",
                """  <build>
    <plugins><plugin>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration><disableXmlReport>true</disableXmlReport></configuration>
    </plugin></plugins>
  </build>
""",
                "custom Surefire disableXmlReport",
            ),
            (
                "owning-rerun-failures",
                "owning",
                """  <build>
    <plugins><plugin>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration><rerunFailingTestsCount>1</rerunFailingTestsCount></configuration>
    </plugin></plugins>
  </build>
""",
                "custom Surefire rerunFailingTestsCount",
            ),
            (
                "owning-rerun-property",
                "owning",
                """  <properties>
    <surefire.rerunFailingTestsCount>1</surefire.rerunFailingTestsCount>
  </properties>
""",
                "surefire.rerunFailingTestsCount property",
            ),
        )
        for index, (name, location, fragment, message) in enumerate(cases):
            with self.subTest(name=name):
                fixture = TargetFixture(self.scratch / f"report-layout-{index}")
                self.target = fixture
                pom = fixture.root / "pom.xml" if location == "reactor" else fixture.module / "pom.xml"
                pom.write_text(
                    pom.read_text(encoding="utf-8").replace(
                        "</project>\n",
                        fragment + "</project>\n",
                    ),
                    encoding="utf-8",
                )
                fixture.commit(f"add unsupported {name}")
                config = self.write_config(fixture.config(), name=f"{name}.json")
                self.assert_rejected_without_target_change(
                    config,
                    self.scratch / f"{name}-output",
                    message,
                )

    def test_rejects_owning_active_by_default_profile(self) -> None:
        pom = self.target.module / "pom.xml"
        pom.write_text(
            pom.read_text(encoding="utf-8").replace(
                "</project>\n",
                """  <profiles>
    <profile>
      <id>target-defaults</id>
      <activation><activeByDefault>TRUE</activeByDefault></activation>
      <properties><target.needed>present</target.needed></properties>
    </profile>
  </profiles>
</project>
""",
            ),
            encoding="utf-8",
        )
        self.target.commit("add active-by-default owning profile")
        config = self.write_config(name="active-by-default.json")
        self.assert_rejected_without_target_change(
            config,
            self.scratch / "active-by-default-output",
            "activeByDefault profiles are outside the assisted runner boundary",
        )

    def test_rejects_preexisting_surefire_execution(self) -> None:
        pom = self.target.module / "pom.xml"
        pom.write_text(
            pom.read_text(encoding="utf-8").replace(
                "</project>\n",
                """  <build><plugins><plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <executions><execution>
      <id>second-test</id>
      <phase>test</phase>
      <goals><goal>test</goal></goals>
    </execution></executions>
  </plugin></plugins></build>
</project>
""",
            ),
            encoding="utf-8",
        )
        self.target.commit("add second Surefire execution")
        config = self.write_config(name="extra-surefire.json")
        self.assert_rejected_without_target_change(
            config,
            self.scratch / "extra-surefire-output",
            "Surefire executions are outside the single-invocation assisted runner boundary",
        )

    def test_rejects_custom_report_layout_in_intermediate_local_parent(self) -> None:
        fixture = TargetFixture(self.scratch / "three-level-target")
        middle = fixture.root / "parent"
        middle.mkdir()
        moved_module = middle / "integration-tests"
        fixture.module.rename(moved_module)
        fixture.module = moved_module
        root_pom = fixture.root / "pom.xml"
        root_pom.write_text(
            root_pom.read_text(encoding="utf-8").replace(
                "<modules><module>integration-tests</module></modules>",
                "<modules><module>parent</module></modules>",
            ),
            encoding="utf-8",
        )
        (middle / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example</groupId>
    <artifactId>target-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
  </parent>
  <artifactId>intermediate-parent</artifactId>
  <packaging>pom</packaging>
  <modules><module>integration-tests</module></modules>
  <build><directory>${project.basedir}/custom-target</directory></build>
</project>
""",
            encoding="utf-8",
        )
        child_pom = moved_module / "pom.xml"
        child_pom.write_text(
            child_pom.read_text(encoding="utf-8")
            .replace("<artifactId>target-parent</artifactId>", "<artifactId>intermediate-parent</artifactId>")
            .replace(
                "    <version>1.0.0-SNAPSHOT</version>\n  </parent>",
                "    <version>1.0.0-SNAPSHOT</version>\n"
                "    <relativePath>../pom.xml</relativePath>\n  </parent>",
            ),
            encoding="utf-8",
        )
        fixture.commit("add intermediate parent with custom report layout")
        self.target = fixture
        config = fixture.config()
        config["owningModule"] = "parent/integration-tests"
        config["reactorSelector"] = "parent/integration-tests/pom.xml"
        path = self.write_config(config, name="intermediate-layout.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "intermediate-layout-output",
            "inherited parent POM parent/pom.xml custom build directory",
        )

    def test_allows_external_parent_above_the_reactor_as_consume_time_boundary(self) -> None:
        root_pom = self.target.root / "pom.xml"
        root_pom.write_text(
            root_pom.read_text(encoding="utf-8").replace(
                "  <modelVersion>4.0.0</modelVersion>\n",
                "  <modelVersion>4.0.0</modelVersion>\n"
                "  <parent>\n"
                "    <groupId>io.example</groupId>\n"
                "    <artifactId>external-parent</artifactId>\n"
                "    <version>1</version>\n"
                "    <relativePath/>\n"
                "  </parent>\n",
            ),
            encoding="utf-8",
        )
        self.target.commit("declare external reactor parent")
        config = self.write_config(self.target.config(), name="external-parent.json")
        output = self.scratch / "external-parent-output"
        result = self.invoke(config, output)
        self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertTrue((output / "routecontract-pilot.patch").is_file())
        self.assertEqual(b"", self.target.status())

    def test_rejects_dtd_non_lf_and_unsafe_unicode_pom(self) -> None:
        pom = self.target.module / "pom.xml"
        text = pom.read_text(encoding="utf-8").replace(
            "<project ",
            "<!DOCTYPE project>\n<project ",
            1,
        )
        pom.write_text(text, encoding="utf-8")
        self.target.commit("add DTD")
        path = self.write_config(self.target.config(), name="dtd.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "dtd-output",
            "must not contain DTD",
        )

        second = TargetFixture(self.scratch / "crlf-target")
        self.target = second
        pom = second.module / "pom.xml"
        pom.write_bytes(pom.read_bytes().replace(b"\n", b"\r\n"))
        second.commit("use CRLF")
        path = self.write_config(second.config(), name="crlf.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "crlf-output",
            "must use LF",
        )

        third = TargetFixture(self.scratch / "bidi-target")
        self.target = third
        pom = third.module / "pom.xml"
        pom.write_text(
            pom.read_text(encoding="utf-8").replace(
                "</project>\n",
                "  <!-- unsafe bidi \u202e marker -->\n</project>\n",
            ),
            encoding="utf-8",
        )
        third.commit("add unsafe bidi control")
        path = self.write_config(third.config(), name="bidi.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "bidi-output",
            "contains an unsafe Unicode character",
        )

        fourth = TargetFixture(self.scratch / "parent-newline-target")
        self.target = fourth
        pom = fourth.module / "pom.xml"
        pom.write_text(
            pom.read_text(encoding="utf-8").replace(
                "    <version>1.0.0-SNAPSHOT</version>\n  </parent>",
                "    <version>1.0.0-SNAPSHOT</version>\n"
                "    <relativePath>../pom.xml\nFORGED_VERIFIED</relativePath>\n"
                "  </parent>",
            ),
            encoding="utf-8",
        )
        fourth.commit("add unsafe parent path newline")
        path = self.write_config(fourth.config(), name="parent-newline.json")
        self.assert_rejected_without_target_change(
            path,
            self.scratch / "parent-newline-output",
            "Maven parent relativePath contains an unsafe Unicode character",
        )


if __name__ == "__main__":
    unittest.main()
