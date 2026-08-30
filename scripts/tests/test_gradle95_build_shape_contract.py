#!/usr/bin/env python3
"""Structural acceptance tests for the Gradle 9.5.1 build-shape lane."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples" / "gradle95-build-shape"
BUILD = FIXTURE / "build.gradle.kts"
README = FIXTURE / "README.md"
WRAPPER = FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.jar"
WRAPPER_PROPERTIES = FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.properties"
TARGET_TEST = (
    FIXTURE
    / "src/test/java/io/github/ym0506/routecontract/examples/buildshape/"
    "DefaultTargetGraphIsolationTest.java"
)
PILOT_TEST = (
    FIXTURE
    / "src/routeContractBuildShapePilot/java/io/github/ym0506/routecontract/"
    "examples/buildshape/RouteContractBuildShapePilotTest.java"
)
VERIFIER = ROOT / "scripts" / "verify-gradle95-build-shape.sh"
VALIDATOR = ROOT / "scripts" / "validate-gradle95-build-shape-receipt.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class Gradle95BuildShapeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.target_test = TARGET_TEST.read_text(encoding="utf-8")
        cls.pilot_test = PILOT_TEST.read_text(encoding="utf-8")
        cls.verifier = VERIFIER.read_text(encoding="utf-8")
        cls.validator = VALIDATOR.read_text(encoding="utf-8")
        cls.ci = CI.read_text(encoding="utf-8")

    def test_fixture_and_wrapper_are_exact_regular_files(self) -> None:
        for path in (
            BUILD,
            README,
            WRAPPER,
            WRAPPER_PROPERTIES,
            TARGET_TEST,
            PILOT_TEST,
            VERIFIER,
            VALIDATOR,
            CI,
        ):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
        self.assertEqual(
            "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7",
            hashlib.sha256(WRAPPER.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            "distributionBase=GRADLE_USER_HOME\n"
            "distributionPath=wrapper/dists\n"
            "distributionSha256Sum="
            "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f\n"
            "distributionUrl=https\\://services.gradle.org/distributions/"
            "gradle-9.5.1-bin.zip\n"
            "networkTimeout=10000\n"
            "retries=0\n"
            "retryBackOffMs=500\n"
            "validateDistributionUrl=true\n"
            "zipStoreBase=GRADLE_USER_HOME\n"
            "zipStorePath=wrapper/dists\n",
            WRAPPER_PROPERTIES.read_text(encoding="utf-8"),
        )

    def test_build_enforces_isolated_dual_jdk_and_two_bom_cells(self) -> None:
        for required in (
            'setOf("3.5.16", "4.1.0")',
            'Set routecontractBootBom to exactly 3.5.16 or 4.1.0',
            'routecontractBootBom must be exactly 3.5.16 or 4.1.0',
            'routecontractPilot must be exactly true or false',
            'routecontractRepository is accepted only when routecontractPilot=true',
            'platform("org.springframework.boot:spring-boot-dependencies:$bootBomVersion")',
            'languageVersion = JavaLanguageVersion.of(21)',
            'sourceSets.create("routeContractBuildShapePilot")',
            'languageVersion = JavaLanguageVersion.of(17)',
            'options.release = 17',
            'exclusiveContent',
            'routeContractBuildShapeRepository',
            'isTransitive = false',
            'routeContractBuildShapeTargetGraph',
            'result.allComponents',
            'result.allDependencies',
            'UnresolvedDependencyResult',
            'Target ResolutionResult must have no unresolved dependency edges',
            '"component|${canonicalComponentId(component.id)}"',
            '"edge|from=$from|requested=${canonicalRequestedId(resolved.requested)}|"',
            '"selected=${canonicalComponentId(resolved.selected.id)}|"',
            "Expected exactly one direct Spring Boot BOM edge",
            "Requested and selected Spring Boot BOM must both be exactly",
            'RouteContract must be absent from the target test runtime graph',
            '"3.5.16" to ("6.3.3" to "5.12.2")',
            '"4.1.0" to ("7.0.2" to "6.0.3")',
            'routeContractBuildShapePilotGraph',
            'routeContractBuildShapeToolchains',
            'routeContractBuildShapeBytecode',
            'mainClassMajor=$mainMajor pilotClassMajor=$pilotMajor',
            'Main and pilot compiled class headers must both be Java 17 major 61',
            'Gradle must run on JDK 21',
            'd25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc',
            '70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d',
        ):
            self.assertIn(required, self.build)
        self.assertNotIn("extendsFrom", self.build)
        self.assertNotIn('id("org.springframework.boot")', self.build)
        self.assertNotIn('id("org.springframework.boot"', self.build)
        self.assertNotIn("spring-boot-starter", self.build)

    def test_runtime_tests_preserve_claim_boundaries(self) -> None:
        for required in (
            "assertEquals(21, Runtime.version().feature())",
            "assertThrows(",
            'Class.forName("io.github.ym0506.routecontract.RouteContract")',
            'Set.of("3.5.16", "4.1.0")',
        ):
            self.assertIn(required, self.target_test)
        for required in (
            "assertEquals(17, Runtime.version().feature())",
            "RouteContract.class.getProtectionDomain()",
            "artifactOrigin=EXACT_LOCAL_RELEASE",
            "adoptionClaim=false",
            "externalTarget=false",
            "baselineApproved=false",
            "candidateChecked=false",
        ):
            self.assertIn(required, self.pilot_test)

    def test_verifier_is_syntax_valid_and_compares_on_off_graphs(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(VERIFIER)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        for required in (
            "gradle-9.5.1-bin.zip",
            "wrapperDistributionSha256=bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f",
            "wrapperJarSha256=497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7",
            "run_cell 3.5.16 off",
            "run_cell 3.5.16 on",
            "run_cell 4.1.0 off",
            "run_cell 4.1.0 on",
            "run_rejected_case missing-bom",
            "target graph changed when the isolated pilot was enabled",
            "pilot graph changed across Spring Boot BOM cells",
            "case GRADLE_USER_HOME must start absent",
            "verifier did not use exactly ten unique case GRADLE_USER_HOME directories",
            "Gradle case failed; final log lines follow",
            'tail -n 120 "$log"',
            "mainClassMajor=61 pilotClassMajor=61",
            "source checkout must start clean",
            "receipt output must be outside the source repository",
            "routecontractPilot must be exactly true or false",
            "routecontractBootBom must be exactly 3.5.16 or 4.1.0",
            "routecontractRepository is accepted only when routecontractPilot=true",
            '"scope": "dependency-management-build-shape-only"',
            '"externalTarget": False',
            '"adoptionClaim": False',
            '"springBootRuntimeCompatibilityClaim": False',
            '"baselineApproved": False',
            '"candidateChecked": False',
            'printf \'%s\\n\' "$success_marker"',
        ):
            self.assertIn(required, self.verifier)

    def test_ci_runs_the_lane_with_both_exact_jdk_homes(self) -> None:
        for required in (
            "gradle95-build-shape:",
            "Gradle 9.5.1 / JDK 21 to 17 / Boot BOM isolation",
            "java-version: '17.0.20+101'",
            "printf 'ROUTECONTRACT_BUILD_SHAPE_JDK17_HOME=%s\\n'",
            "java-version: '21.0.12+8'",
            "verify-gradle95-build-shape.sh",
            '--jdk17-home "${ROUTECONTRACT_BUILD_SHAPE_JDK17_HOME}"',
            "build-shape-receipt.json",
            "validate-gradle95-build-shape-receipt.py",
            "receipt-validation.txt",
        ):
            self.assertIn(required, self.ci)

    @staticmethod
    def valid_receipt(repository: Path = ROOT) -> dict[str, object]:
        source_revision = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        source_tree = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD^{tree}"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        return {
            "schemaVersion": 1,
            "kind": "routecontract-gradle95-build-shape-receipt",
            "result": "PASS",
            "scope": "dependency-management-build-shape-only",
            "sourceRevision": source_revision,
            "sourceTree": source_tree,
            "sourceClean": True,
            "gradle": {
                "version": "9.5.1",
                "distributionSha256": (
                    "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f"
                ),
                "wrapperJarSha256": (
                    "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"
                ),
                "runtimeJdkFeature": 21,
            },
            "toolchains": {
                "mainCompiler": 21,
                "mainBytecodeRelease": 17,
                "targetTestLauncher": 21,
                "pilotCompiler": 17,
                "pilotBytecodeRelease": 17,
                "pilotTestLauncher": 17,
                "measuredMainClassMajor": 61,
                "measuredPilotClassMajor": 61,
            },
            "bootBomCells": {
                "3.5.16": {"targetGraphSha256": "1" * 64},
                "4.1.0": {"targetGraphSha256": "2" * 64},
            },
            "pilotGraphSha256": "3" * 64,
            "artifact": {
                "coordinate": (
                    "io.github.ym0506.routecontract:"
                    "routecontract-shardingsphere-5.5:0.1.2"
                ),
                "jarSha256": (
                    "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
                ),
                "pomSha256": (
                    "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d"
                ),
                "origin": "exact-local-release-repository",
            },
            "targetGraphUnchangedWhenPilotEnabled": True,
            "routeContractAbsentFromTargetGraph": True,
            "isolation": {
                "caseGradleUserHomes": 10,
                "uniqueInitiallyAbsent": True,
                "dependencyCachesShared": False,
                "wrapperDistributionSeedOnly": True,
            },
            "externalTarget": False,
            "externalRepositoryExecuted": False,
            "adoptionClaim": False,
            "springBootRuntimeCompatibilityClaim": False,
            "springBootStarterCompatibilityClaim": False,
            "representativeDatabaseOperationExecuted": False,
            "baselineApproved": False,
            "candidateChecked": False,
        }

    def test_independent_receipt_validator_accepts_exact_and_rejects_claim_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_minimal_validator_repository(root)
            validator = repository / "scripts" / VALIDATOR.name
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps(
                    self.valid_receipt(repository), indent=2, sort_keys=True
                ) + "\n",
                encoding="utf-8",
            )
            accepted = subprocess.run(
                ["python3", "-I", str(validator), str(receipt)],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertEqual(
                "ROUTECONTRACT_GRADLE95_BUILD_SHAPE_RECEIPT VALID\n",
                accepted.stdout,
            )
            mutations = (
                (("adoptionClaim",), True, "adoptionClaim must be exactly False"),
                (("schemaVersion",), True, "schemaVersion must be exactly 1"),
                (
                    ("sourceRevision",),
                    "0" * 40,
                    "sourceRevision does not match this checkout HEAD",
                ),
                (
                    ("gradle", "runtimeJdkFeature"),
                    True,
                    "gradle.runtimeJdkFeature must be exactly 21",
                ),
                (
                    ("toolchains", "mainCompiler"),
                    True,
                    "toolchains.mainCompiler must be exactly 21",
                ),
                (
                    ("isolation", "caseGradleUserHomes"),
                    True,
                    "isolation.caseGradleUserHomes must be exactly 10",
                ),
            )
            for keys, replacement, expected_error in mutations:
                with self.subTest(keys=keys):
                    changed = json.loads(json.dumps(self.valid_receipt(repository)))
                    target = changed
                    for key in keys[:-1]:
                        target = target[key]
                    target[keys[-1]] = replacement
                    receipt.write_text(
                        json.dumps(changed, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    rejected = subprocess.run(
                        ["python3", "-I", str(validator), str(receipt)],
                        capture_output=True,
                        check=False,
                        text=True,
                    )
                    self.assertEqual(1, rejected.returncode)
                    self.assertIn(expected_error, rejected.stderr)

    def make_minimal_validator_repository(self, root: Path) -> Path:
        repository = root / "validator-repo"
        scripts = repository / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(VALIDATOR, scripts / VALIDATOR.name)
        (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "-c",
                "user.name=RouteContract Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-q",
                "-m",
                "validator fixture",
            ],
            check=True,
        )
        return repository

    def test_independent_validator_rejects_tracked_and_untracked_source_dirt(
        self,
    ) -> None:
        for dirty_kind in ("tracked", "untracked"):
            with self.subTest(dirty_kind=dirty_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                repository = self.make_minimal_validator_repository(root)
                receipt = root / "receipt.json"
                receipt.write_text(
                    json.dumps(
                        self.valid_receipt(repository), indent=2, sort_keys=True
                    ) + "\n",
                    encoding="utf-8",
                )
                if dirty_kind == "tracked":
                    (repository / "tracked.txt").write_text(
                        "changed\n", encoding="utf-8"
                    )
                else:
                    (repository / "untracked.txt").write_text(
                        "dirty\n", encoding="utf-8"
                    )
                completed = subprocess.run(
                    [
                        "python3",
                        "-I",
                        str(repository / "scripts" / VALIDATOR.name),
                        str(receipt),
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                )
                self.assertEqual(1, completed.returncode)
                self.assertIn(
                    "source checkout must be clean when validating the receipt",
                    completed.stderr,
                )

    def make_minimal_verifier_repository(self, root: Path) -> Path:
        repository = root / "repo"
        fixture = repository / "examples" / "gradle95-build-shape"
        wrapper = fixture / "gradle" / "wrapper"
        scripts = repository / "scripts"
        wrapper.mkdir(parents=True)
        scripts.mkdir(parents=True)
        shutil.copy2(VERIFIER, scripts / VERIFIER.name)
        for path in (
            fixture / "build.gradle.kts",
            fixture / "settings.gradle.kts",
            fixture / "gradlew",
            wrapper / "gradle-wrapper.jar",
            wrapper / "gradle-wrapper.properties",
            scripts / "install-release-assets.py",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"placeholder\n")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "-c",
                "user.name=RouteContract Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-q",
                "-m",
                "fixture",
            ],
            check=True,
        )
        return repository

    def run_early_verifier_rejection(
        self, repository: Path, receipt: Path
    ) -> subprocess.CompletedProcess[str]:
        assets = repository.parent / "assets"
        jdk = repository.parent / "jdk"
        assets.mkdir(exist_ok=True)
        jdk.mkdir(exist_ok=True)
        environment = os.environ.copy()
        environment["JAVA_HOME"] = str(jdk)
        return subprocess.run(
            [
                "bash",
                str(repository / "scripts" / VERIFIER.name),
                "--release-assets-dir",
                str(assets),
                "--jdk17-home",
                str(jdk),
                "--receipt-output",
                str(receipt),
            ],
            capture_output=True,
            check=False,
            text=True,
            env=environment,
        )

    def test_verifier_rejects_in_repository_receipt_and_dirty_sources(self) -> None:
        for dirty_kind in ("tracked", "untracked"):
            with self.subTest(dirty_kind=dirty_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                repository = self.make_minimal_verifier_repository(root)
                if dirty_kind == "tracked":
                    (repository / "examples/gradle95-build-shape/settings.gradle.kts").write_text(
                        "changed\n", encoding="utf-8"
                    )
                else:
                    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
                completed = self.run_early_verifier_rejection(
                    repository, root / "outside-receipt.json"
                )
                self.assertEqual(1, completed.returncode)
                self.assertIn("source checkout must start clean", completed.stderr)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_minimal_verifier_repository(root)
            completed = self.run_early_verifier_rejection(
                repository, repository / "receipt.json"
            )
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "receipt output must be outside the source repository",
                completed.stderr,
            )

    def test_documentation_states_the_non_claims(self) -> None:
        normalized = " ".join(self.readme.split())
        for required in (
            "dependency-management and JVM build-shape evidence only",
            "does **not** run Spring Boot",
            "does not add or validate a Spring Boot starter",
            "does not exercise an external repository",
            "does not establish adoption",
            "creates no baseline or candidate",
        ):
            self.assertIn(required, normalized)


if __name__ == "__main__":
    unittest.main()
