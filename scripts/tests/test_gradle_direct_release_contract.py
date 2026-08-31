#!/usr/bin/env python3
"""Structural acceptance tests for the direct immutable Release Gradle lane."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples" / "gradle-direct-release"
BUILD = FIXTURE / "build.gradle.kts"
README = FIXTURE / "README.md"
METADATA = FIXTURE / "gradle" / "verification-metadata.xml"
LOCKFILE = FIXTURE / "gradle.lockfile"
PROBE = (
    FIXTURE
    / "src/main/java/io/github/ym0506/routecontract/directrelease/"
    "DirectReleaseRuntimeProbe.java"
)
VERIFIER = ROOT / "scripts" / "verify-gradle-direct-release.py"
WRAPPER_SOURCE = ROOT / "examples" / "gradle95-build-shape"
WRAPPER_ROOT = FIXTURE
NS = {"v": "https://schema.gradle.org/dependency-verification"}
ROUTECONTRACT_SHA256 = (
    "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GradleDirectReleaseContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.probe = PROBE.read_text(encoding="utf-8")
        cls.verifier = VERIFIER.read_text(encoding="utf-8")
        cls.lock = LOCKFILE.read_text(encoding="utf-8")
        cls.metadata_tree = ET.parse(METADATA)
        cls.metadata_root = cls.metadata_tree.getroot()

    def test_fixture_is_nested_and_does_not_change_root_graph(self) -> None:
        settings = (FIXTURE / "settings.gradle.kts").read_text(encoding="utf-8")
        self.assertEqual(
            'rootProject.name = "routecontract-gradle-direct-release"\n', settings
        )
        root_settings = (ROOT / "settings.gradle").read_text(encoding="utf-8")
        self.assertNotIn("gradle-direct-release", root_settings)
        self.assertNotIn("gradle-direct-release", (ROOT / "build.gradle").read_text(
            encoding="utf-8"
        ))

    def test_exact_release_and_exclusive_artifact_only_repository(self) -> None:
        required = (
            'val routeContractVersion = "0.1.2"',
            "https://github.com/ym0506/routecontract/releases/download/v0.1.2",
            'val routeContractSize = 75_891L',
            ROUTECONTRACT_SHA256,
            "exclusiveContent",
            'artifact("[artifact]-[revision](-[classifier]).[ext]")',
            "metadataSources",
            "artifact()",
            "isTransitive = false",
            "inputs.files(routeContractArtifactCollection.artifactFiles)",
            'withPropertyName("strictlyVerifiedMavenRuntimeClosure")',
            "StandardCopyOption.ATOMIC_MOVE",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.build)
        self.assertNotIn("mavenLocal()", self.build)
        self.assertNotIn("jitpack", self.build.lower())
        self.assertNotRegex(self.build, r"routecontract(Test|Expected|BaseUrl).*Property")
        self.assertIn(
            "lockMode.set(org.gradle.api.artifacts.dsl.LockMode.STRICT)", self.build
        )

    def test_jdk17_and_all_shardingsphere_553_are_fail_closed(self) -> None:
        for value in (
            "JavaVersion.current() != JavaVersion.VERSION_17",
            "languageVersion = JavaLanguageVersion.of(17)",
            "options.release.set(17)",
            'val shardingSphereVersion = "5.5.3"',
            'requested.group == "org.apache.shardingsphere"',
            "it.version != shardingSphereVersion",
        ):
            self.assertIn(value, self.build)
        self.assertIn("Runtime.version().feature() == 17", self.probe)
        sharding_lines = [
            line
            for line in self.lock.splitlines()
            if line.startswith("org.apache.shardingsphere:")
        ]
        self.assertGreaterEqual(len(sharding_lines), 20)
        self.assertTrue(all(":5.5.3=" in line for line in sharding_lines))
        jackson_lines = [
            line
            for line in self.lock.splitlines()
            if line.startswith("com.fasterxml.jackson:")
            or line.startswith("com.fasterxml.jackson.")
        ]
        self.assertGreaterEqual(len(jackson_lines), 6)
        self.assertIn(
            "com.fasterxml.jackson.core:jackson-annotations:2.21=",
            self.lock,
        )
        self.assertTrue(
            all(
                ":2.18.9=" in line
                for line in jackson_lines
                if not line.startswith(
                    "com.fasterxml.jackson.core:jackson-annotations:"
                )
            )
        )
        self.assertIn(
            'implementation(platform("com.fasterxml.jackson:jackson-bom:2.18.9"))',
            self.build,
        )
        self.assertNotIn("enforcedPlatform", self.build)
        self.assertIn("wrongFasterXmlJackson", self.build)

    def test_lockfile_and_strict_full_closure_verification_metadata(self) -> None:
        configuration = self.metadata_root.find("v:configuration", NS)
        self.assertIsNotNone(configuration)
        self.assertEqual("true", configuration.findtext("v:verify-metadata", namespaces=NS))
        self.assertEqual("false", configuration.findtext("v:verify-signatures", namespaces=NS))
        self.assertIsNone(configuration.find("v:trusted-artifacts", NS))
        self.assertIsNone(configuration.find("v:trusted-keys", NS))

        components: dict[tuple[str, str, str], ET.Element] = {}
        artifacts = []
        for component in self.metadata_root.findall("v:components/v:component", NS):
            key = (
                component.attrib["group"],
                component.attrib["name"],
                component.attrib["version"],
            )
            self.assertNotIn(key, components)
            components[key] = component
            for artifact in component.findall("v:artifact", NS):
                checksums = artifact.findall("v:sha256", NS)
                self.assertGreaterEqual(len(checksums), 1, artifact.attrib["name"])
                for checksum in checksums:
                    self.assertRegex(checksum.attrib["value"], r"^[0-9a-f]{64}$")
                artifacts.append(artifact)
        self.assertGreaterEqual(len(components), 45)
        self.assertGreaterEqual(len(artifacts), 150)

        selected = set()
        for line in self.lock.splitlines():
            if not line or line.startswith("#") or line.startswith("empty="):
                continue
            coordinate = line.split("=", 1)[0]
            group, name, version = coordinate.split(":", 2)
            selected.add((group, name, version))
        self.assertGreaterEqual(len(selected), 45)
        self.assertFalse(selected - components.keys())

        route_component = components[
            (
                "io.github.ym0506.routecontract",
                "routecontract-shardingsphere-5.5",
                "0.1.2",
            )
        ]
        route_artifacts = route_component.findall("v:artifact", NS)
        self.assertEqual(1, len(route_artifacts))
        self.assertEqual(
            "routecontract-shardingsphere-5.5-0.1.2.jar",
            route_artifacts[0].attrib["name"],
        )
        self.assertEqual(
            ROUTECONTRACT_SHA256,
            route_artifacts[0].find("v:sha256", NS).attrib["value"],
        )

    def test_provider_type_origin_is_checked_before_instantiation(self) -> None:
        descriptor = self.probe.index("verifyDescriptor(routeContractJar);")
        stream = self.probe.index("ServiceLoader\n                .load")
        provider_type = self.probe.index("javaProviderHandle.type()")
        provider_origin = self.probe.index("Path providerTypeOrigin = codeSource(providerType)")
        provider_rehash = self.probe.index("sha256(providerTypeOrigin).equals")
        provider_get = self.probe.index("javaProviderHandle.get()")
        sharding_loader = self.probe.index(
            "ShardingSphereServiceLoader.getServiceInstances"
        )
        self.assertLess(descriptor, stream)
        self.assertLess(stream, provider_type)
        self.assertLess(provider_type, provider_origin)
        self.assertLess(provider_origin, provider_rehash)
        self.assertLess(provider_rehash, provider_get)
        self.assertLess(provider_get, sharding_loader)
        self.assertIn(
            "post-verification compatibility probe, not a pre-instantiation trust boundary",
            self.probe,
        )
        self.assertIn(
            "routecontractShardingSphereLoaderRole=post-verification-compatibility",
            self.probe,
        )
        for anchor in (
            "connection instanceof JarURLConnection",
            "jarConnection.getEntryName()",
            "jarConnection.getJarFileURL()",
            '"file".equals(jarUrl.getProtocol())',
            "Path.of(jarUrl.toURI()).toRealPath()",
            "matchingOrigins.equals(List.of(routeContractJar))",
        ):
            self.assertIn(anchor, self.probe)

    def test_verifier_starts_with_fresh_online_wrong_sha_resolution(self) -> None:
        first_case = self.verifier.index('temporary / "01-wrong-verification-sha"')
        first_precondition = self.verifier.index(
            "fresh_cache_precondition(wrong_verification_home", first_case
        )
        first_invoke = self.verifier.index("wrong_verification = invoke(", first_case)
        metadata_case = self.verifier.index('temporary / "03-wrong-maven-metadata"')
        positive = self.verifier.index('temporary / "04-positive"')
        self.assertLess(first_case, first_precondition)
        self.assertLess(first_precondition, first_invoke)
        self.assertLess(first_invoke, metadata_case)
        self.assertLess(metadata_case, positive)
        self.assertIn('"--refresh-dependencies", "verifyRouteContractArtifact"', self.verifier)
        self.assertIn('"--dependency-verification=strict"', self.verifier)
        self.assertIn('"Dependency verification failed"', self.verifier)
        self.assertIn("ROUTECONTRACT_ARTIFACT_SHA256_MISMATCH", self.verifier)
        self.assertIn("transmittable-thread-local-2.14.2.pom", self.verifier)
        self.assertIn("wrongShaFirstResolution=fresh-online-cache-rejected", self.verifier)

    def test_exact_reviewed_gradle_951_wrapper_is_used(self) -> None:
        expected = {
            "gradlew": "ab5c0cad16305af2e619c159c1f58dd68d07fab9c11e36701e109c0277407f7a",
            "gradlew.bat": "475c4f08cd57cf2faa819e7f36d72aa93f0ad646ea23a8f7fa3ef54dee1cbc52",
            "gradle/wrapper/gradle-wrapper.jar": (
                "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"
            ),
            "gradle/wrapper/gradle-wrapper.properties": (
                "9caeb142fade370957e5e9cd95a83441bbe41f73a1863398dd5467695853332e"
            ),
        }
        for relative, digest in expected.items():
            with self.subTest(relative=relative):
                self.assertEqual(digest, sha256(WRAPPER_ROOT / relative))
                self.assertEqual(
                    (WRAPPER_SOURCE / relative).read_bytes(),
                    (WRAPPER_ROOT / relative).read_bytes(),
                )
                expected_mode = 0o755 if relative == "gradlew" else 0o644
                self.assertEqual(
                    expected_mode,
                    stat.S_IMODE((WRAPPER_ROOT / relative).stat().st_mode),
                )
        properties = (WRAPPER_ROOT / "gradle/wrapper/gradle-wrapper.properties").read_text(
            encoding="utf-8"
        )
        self.assertIn("gradle-9.5.1-bin.zip", properties)
        self.assertIn(
            "distributionSha256Sum="
            "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f",
            properties,
        )
        self.assertIn(
            "WRAPPER_ROOT = FIXTURE",
            self.verifier,
        )
        self.assertIn('str(project / "gradlew")', self.verifier)

    def test_check_executes_the_runtime_probe(self) -> None:
        check_block = self.build[self.build.index('tasks.named("check")') :]
        self.assertIn('dependsOn(tasks.named("run"))', check_block)
        self.assertIn("Runtime classpath must contain the staged RouteContract JAR exactly once", self.build)

    def test_docs_preserve_candidate_human_approval_and_ci_boundary(self) -> None:
        required = (
            "representative ShardingSphere-JDBC operation",
            "business-result assertion",
            "exact candidate bytes",
            "human authorized to approve changes",
            "upstream public CI",
            "--dependency-verification=strict",
            "is not adoption and is not an actual user",
            "post-verification compatibility assertion",
            "not claimed as a pre-instantiation security boundary",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.readme)
        candidate = self.readme.index("writes only a separate candidate")
        human = self.readme.index("A human authorized to approve changes")
        ci = self.readme.index("upstream public CI")
        self.assertLess(candidate, human)
        self.assertLess(human, ci)

    def test_source_tree_has_no_generated_state(self) -> None:
        forbidden = (
            FIXTURE / ".gradle",
            FIXTURE / "build",
            FIXTURE / "gradle-user-home",
            FIXTURE / "project-cache",
            FIXTURE / "test-results",
        )
        self.assertEqual([], [path for path in forbidden if path.exists()])
        self.assertEqual([], list(FIXTURE.rglob("*.log")))
        ignored = (FIXTURE / ".gitignore").read_text(encoding="utf-8").splitlines()
        for value in (
            ".gradle/",
            "build/",
            "gradle-user-home/",
            "project-cache/",
            "test-results/",
            "*.log",
        ):
            self.assertIn(value, ignored)


if __name__ == "__main__":
    unittest.main()
