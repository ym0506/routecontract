from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-external-maven-integration.sh"
VALID_SOURCE_POM = (
    REPOSITORY_ROOT / "examples" / "maven-pilot" / "integration-tests" / "pom.xml"
).read_text(encoding="utf-8")
VALID_GRAPH = """\
[INFO] --- dependency:3.11.0:tree (default-cli) @ consumer ---
[INFO] example:consumer:jar:1.0.0
[INFO] +- org.apache.shardingsphere:shardingsphere-jdbc:jar:5.5.3:compile
[INFO] +- org.apache.calcite:calcite-core:jar:1.42.0:compile
[INFO] |  +- net.minidev:json-smart:jar:2.4.10:runtime
[INFO] |     \\- net.minidev:accessors-smart:jar:2.4.9:compile
[INFO] +- org.apache.calcite:calcite-linq4j:jar:1.42.0:test
[INFO] +- com.fasterxml.jackson.core:jackson-databind:jar:2.18.9:compile
[INFO] \\- io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:jar:0.1.2:test
"""
VALID_PROFILE_OFF_EFFECTIVE_POM = """\
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>consumer</artifactId>
  <version>1.0.0</version>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>example</groupId>
        <artifactId>production-bom</artifactId>
        <version>1.0.0</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.apache.shardingsphere</groupId>
      <artifactId>shardingsphere-jdbc</artifactId>
      <version>5.5.3</version>
      <exclusions>
        <exclusion>
          <groupId>example</groupId>
          <artifactId>unrelated-production-exclusion</artifactId>
        </exclusion>
      </exclusions>
    </dependency>
    <dependency>
      <groupId>com.mysql</groupId>
      <artifactId>mysql-connector-j</artifactId>
      <version>8.4.0</version>
    </dependency>
  </dependencies>
  <repositories>
    <repository>
      <id>production-repository</id>
      <url>https://repo.example.invalid/releases</url>
    </repository>
  </repositories>
  <build>
    <plugins>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>build-helper-maven-plugin</artifactId>
        <executions>
          <execution>
            <configuration>
              <sources><source>src/generated/java</source></sources>
            </configuration>
          </execution>
        </executions>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <executions>
          <execution>
            <id>default-test</id>
            <phase>test</phase>
            <goals><goal>test</goal></goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
"""
VALID_PROFILE_ON_EFFECTIVE_POM = """\
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>consumer</artifactId>
  <version>1.0.0</version>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.4</version>
        <configuration>
          <reportsDirectory>${project.basedir}/target/surefire-reports</reportsDirectory>
          <reportNameSuffix></reportNameSuffix>
          <disableXmlReport>false</disableXmlReport>
          <promoteUserPropertiesToSystemProperties>false</promoteUserPropertiesToSystemProperties>
          <rerunFailingTestsCount>0</rerunFailingTestsCount>
          <systemPropertyVariables>
            <routecontract.projectDir>${project.basedir}</routecontract.projectDir>
            <routecontract.candidateRoot>target/routecontract</routecontract.candidateRoot>
            <routecontract.artifactJarName>routecontract-shardingsphere-5.5-0.1.2.jar</routecontract.artifactJarName>
            <routecontract.artifactJarPath>${routecontract.artifactJarPath}</routecontract.artifactJarPath>
          </systemPropertyVariables>
        </configuration>
        <executions>
          <execution>
            <id>default-test</id>
            <phase>test</phase>
            <goals><goal>test</goal></goals>
            <configuration>
              <reportsDirectory>${project.basedir}/target/surefire-reports</reportsDirectory>
              <reportNameSuffix></reportNameSuffix>
              <disableXmlReport>false</disableXmlReport>
              <promoteUserPropertiesToSystemProperties>false</promoteUserPropertiesToSystemProperties>
              <rerunFailingTestsCount>0</rerunFailingTestsCount>
              <systemPropertyVariables>
                <routecontract.projectDir>${project.basedir}</routecontract.projectDir>
                <routecontract.candidateRoot>target/routecontract</routecontract.candidateRoot>
                <routecontract.artifactJarName>routecontract-shardingsphere-5.5-0.1.2.jar</routecontract.artifactJarName>
                <routecontract.artifactJarPath>${routecontract.artifactJarPath}</routecontract.artifactJarPath>
              </systemPropertyVariables>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
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

    def _run_effective_pom_parser(
        self, effective_pom: str
    ) -> subprocess.CompletedProcess[str]:
        script = SCRIPT.read_text(encoding="utf-8")
        marker = 'python3 -I - "$profile_off_effective_pom" <<\'PY\'\n'
        start = script.index(marker) + len(marker)
        parser = script[start : script.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            pom_path = Path(temporary) / "effective-pom.xml"
            pom_path.write_text(effective_pom, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-I", "-c", parser, pom_path],
                capture_output=True,
                check=False,
                text=True,
            )

    def _run_source_pom_parser(
        self, source_pom: str
    ) -> subprocess.CompletedProcess[str]:
        script = SCRIPT.read_text(encoding="utf-8")
        marker = 'python3 -I - "$ROUTECONTRACT_OWNING_POM" <<\'PY\'\n'
        start = script.index(marker) + len(marker)
        parser = script[start : script.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            pom_path = Path(temporary) / "pom.xml"
            pom_path.write_text(source_pom, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-I", "-c", parser, pom_path],
                capture_output=True,
                check=False,
                text=True,
            )

    def _run_profile_on_effective_pom_parser(
        self, effective_pom: str
    ) -> subprocess.CompletedProcess[str]:
        script = SCRIPT.read_text(encoding="utf-8")
        marker = '    "$cached_jar" <<\'PY\'\n'
        start = script.index(marker) + len(marker)
        parser = script[start : script.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            pom_path = Path(temporary) / "profile-on-effective-pom.xml"
            owning_directory = pom_path.parent.resolve(strict=True)
            owning_target = owning_directory / "target"
            cached_jar = owning_directory / "cache" / "routecontract.jar"
            materialized = effective_pom.replace(
                "${project.basedir}", os.fspath(owning_directory)
            ).replace(
                "${routecontract.artifactJarPath}", os.fspath(cached_jar)
            )
            pom_path.write_text(materialized, encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    parser,
                    pom_path,
                    owning_directory,
                    owning_target,
                    cached_jar,
                ],
                capture_output=True,
                check=False,
                text=True,
            )

    def _run_selected_report_parser(
        self, *, retry_element: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        script = SCRIPT.read_text(encoding="utf-8")
        marker = '    "$ROUTECONTRACT_APPROVED_PATH" <<\'PY\'\n'
        start = script.index(marker) + len(marker)
        parser = script[start : script.index("\nPY\n", start)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            report = root / "TEST-pilot.xml"
            candidate = root / "candidate.json"
            approved = root / "approved.json"
            suite = ET.Element(
                "testsuite",
                tests="1",
                failures="1",
                errors="0",
                skipped="0",
            )
            case = ET.SubElement(
                suite,
                "testcase",
                classname="example.ContractTest",
                name="capturesCandidate",
            )
            ET.SubElement(
                case,
                "failure",
                message=(
                    f"No approved baseline. Review {candidate} and copy it to "
                    f"{approved} only after human approval."
                ),
            )
            if retry_element is not None:
                ET.SubElement(case, retry_element)
            report.write_bytes(ET.tostring(suite, encoding="utf-8"))
            return subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    parser,
                    "review",
                    report,
                    "example.ContractTest",
                    "capturesCandidate",
                    candidate,
                    approved,
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
            "owning source POM must contain exactly one routecontract-pilot profile",
            "routecontract-pilot activation property changed",
            "routecontract-pilot Jackson BOM import boundary changed",
            "RouteContract dependency escaped routecontract-pilot",
            "RouteContract repository escaped routecontract-pilot",
            "RouteContract pilot source escaped routecontract-pilot",
            "profile-off effective POM activated a RouteContract dependency",
            "profile-off effective POM activated the RouteContract repository",
            "profile-off effective POM activated the pilot source root",
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

    def test_profile_off_effective_pom_accepts_isolated_profile(self) -> None:
        completed = self._run_effective_pom_parser(
            VALID_PROFILE_OFF_EFFECTIVE_POM
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_effective_poms_enforce_single_surefire_invocation(self) -> None:
        profile_on = self._run_profile_on_effective_pom_parser(
            VALID_PROFILE_ON_EFFECTIVE_POM
        )
        self.assertEqual(0, profile_on.returncode, profile_on.stderr)

        extra_execution = """\
          <execution>
            <id>second-test</id>
            <phase>test</phase>
            <goals><goal>test</goal></goals>
          </execution>
"""
        profile_on_extra = self._run_profile_on_effective_pom_parser(
            VALID_PROFILE_ON_EFFECTIVE_POM.replace(
                "        </executions>",
                extra_execution + "        </executions>",
                1,
            )
        )
        self.assertNotEqual(0, profile_on_extra.returncode)
        self.assertIn("one Surefire execution", profile_on_extra.stderr)

        profile_on_rerun = self._run_profile_on_effective_pom_parser(
            VALID_PROFILE_ON_EFFECTIVE_POM.replace(
                "<rerunFailingTestsCount>0</rerunFailingTestsCount>",
                "<rerunFailingTestsCount>1</rerunFailingTestsCount>",
                1,
            )
        )
        self.assertNotEqual(0, profile_on_rerun.returncode)
        self.assertIn("rerunFailingTestsCount is not exact", profile_on_rerun.stderr)

        inherited_profile_off_execution = """\
          <execution>
            <id>second-test</id>
            <phase>test</phase>
            <goals><goal>test</goal></goals>
          </execution>
"""
        profile_off_extra = self._run_effective_pom_parser(
            VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                "            <goals><goal>test</goal></goals>\n"
                "          </execution>\n"
                "        </executions>\n"
                "      </plugin>\n"
                "    </plugins>",
                "            <goals><goal>test</goal></goals>\n"
                "          </execution>\n"
                + inherited_profile_off_execution
                + "        </executions>\n"
                "      </plugin>\n"
                "    </plugins>",
                1,
            )
        )
        self.assertNotEqual(0, profile_off_extra.returncode)
        self.assertIn("one Surefire execution", profile_off_extra.stderr)

        profile_off_retry_property = self._run_effective_pom_parser(
            VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                "  <modelVersion>4.0.0</modelVersion>",
                "  <modelVersion>4.0.0</modelVersion>\n"
                "  <properties><surefire.rerunFailingTestsCount>1"
                "</surefire.rerunFailingTestsCount></properties>",
                1,
            )
        )
        self.assertNotEqual(0, profile_off_retry_property.returncode)
        self.assertIn("enables Surefire test retries", profile_off_retry_property.stderr)

    def test_selected_report_rejects_retry_evidence(self) -> None:
        accepted = self._run_selected_report_parser()
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        for element in (
            "rerunFailure",
            "rerunError",
            "flakyFailure",
            "flakyError",
        ):
            with self.subTest(element=element):
                rejected = self._run_selected_report_parser(retry_element=element)
                self.assertNotEqual(0, rejected.returncode)
                self.assertIn("retry evidence", rejected.stderr)

    def test_source_pom_accepts_exact_profile_nesting(self) -> None:
        completed = self._run_source_pom_parser(VALID_SOURCE_POM)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_source_pom_allows_existing_production_graph_controls(self) -> None:
        production_management = """\
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.fasterxml.jackson</groupId>
        <artifactId>jackson-bom</artifactId>
        <version>2.18.9</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

"""
        production_calcite = """\
    <dependency>
      <groupId>org.apache.calcite</groupId>
      <artifactId>calcite-core</artifactId>
      <version>1.42.0</version>
      <scope>compile</scope>
      <exclusions>
        <exclusion>
          <groupId>org.locationtech.jts.io</groupId>
          <artifactId>jts-io-common</artifactId>
        </exclusion>
      </exclusions>
    </dependency>
"""
        source_pom = VALID_SOURCE_POM.replace(
            "  <dependencies>", production_management + "  <dependencies>", 1
        ).replace(
            "  </dependencies>\n\n  <build>",
            production_calcite + "  </dependencies>\n\n  <build>",
            1,
        )
        completed = self._run_source_pom_parser(source_pom)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_source_pom_rejects_profile_boundary_mutations(self) -> None:
        routecontract_dependency = """\
    <dependency>
      <groupId>io.github.ym0506.routecontract</groupId>
      <artifactId>routecontract-shardingsphere-5.5</artifactId>
      <version>0.1.2</version>
      <scope>test</scope>
    </dependency>
"""
        leaked_repository = """\
  <repositories>
    <repository>
      <id>routecontract-verified-file-repository</id>
      <url>${routecontractRepositoryUrl}</url>
    </repository>
  </repositories>

"""
        leaked_source_plugin = """\
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>build-helper-maven-plugin</artifactId>
        <executions><execution><configuration><sources>
          <source>src/routeContractPilot/java</source>
        </sources></configuration></execution></executions>
      </plugin>
"""
        mutations = {
            "missing exact profile": VALID_SOURCE_POM.replace(
                "<id>routecontract-pilot</id>",
                "<id>routecontract-pilot-renamed</id>",
                1,
            ),
            "activation enabled by default": VALID_SOURCE_POM.replace(
                "<activation>\n        <property>",
                "<activation>\n        <activeByDefault>true</activeByDefault>\n"
                "        <property>",
                1,
            ),
            "activation value changed": VALID_SOURCE_POM.replace(
                "<value>true</value>", "<value>false</value>", 1
            ),
            "Jackson BOM missing": VALID_SOURCE_POM.replace(
                "<artifactId>jackson-bom</artifactId>",
                "<artifactId>jackson-bom-missing</artifactId>",
                1,
            ),
            "required exclusion missing": VALID_SOURCE_POM.replace(
                "<artifactId>jts-io-common</artifactId>",
                "<artifactId>jts-io-common-missing</artifactId>",
                1,
            ),
            "repository policy changed": VALID_SOURCE_POM.replace(
                "<checksumPolicy>fail</checksumPolicy>",
                "<checksumPolicy>warn</checksumPolicy>",
                1,
            ),
            "source execution changed": VALID_SOURCE_POM.replace(
                "<source>src/routeContractPilot/java</source>",
                "<source>src/test/java</source>",
                1,
            ),
            "Surefire property changed": VALID_SOURCE_POM.replace(
                "<routecontract.candidateRoot>target/routecontract"
                "</routecontract.candidateRoot>",
                "<routecontract.candidateRoot>target/other"
                "</routecontract.candidateRoot>",
                1,
            ),
            "Surefire retry count changed": VALID_SOURCE_POM.replace(
                "<rerunFailingTestsCount>0</rerunFailingTestsCount>",
                "<rerunFailingTestsCount>1</rerunFailingTestsCount>",
                1,
            ),
            "RouteContract dependency escaped": VALID_SOURCE_POM.replace(
                "  </dependencies>\n\n  <build>",
                routecontract_dependency + "  </dependencies>\n\n  <build>",
                1,
            ),
            "RouteContract repository escaped": VALID_SOURCE_POM.replace(
                "  <build>", leaked_repository + "  <build>", 1
            ),
            "pilot source escaped": VALID_SOURCE_POM.replace(
                "    </plugins>\n  </build>\n\n  <profiles>",
                leaked_source_plugin
                + "    </plugins>\n  </build>\n\n  <profiles>",
                1,
            ),
        }
        for name, source_pom in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(VALID_SOURCE_POM, source_pom)
                completed = self._run_source_pom_parser(source_pom)
                self.assertNotEqual(0, completed.returncode)

    def test_profile_off_effective_pom_allows_non_pilot_versions(self) -> None:
        management_anchor = """\
      <dependency>
        <groupId>example</groupId>
        <artifactId>production-bom</artifactId>
        <version>1.0.0</version>
      </dependency>"""
        dependency_anchor = """\
    <dependency>
      <groupId>com.mysql</groupId>
      <artifactId>mysql-connector-j</artifactId>
      <version>8.4.0</version>
    </dependency>"""
        non_pilot_versions = VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
            management_anchor,
            management_anchor
            + """
      <dependency>
        <groupId>com.fasterxml.jackson</groupId>
        <artifactId>jackson-bom</artifactId>
        <version>2.19.0</version>
      </dependency>
      <dependency>
        <groupId>org.apache.calcite</groupId>
        <artifactId>calcite-linq4j</artifactId>
        <version>1.41.0</version>
      </dependency>
      <dependency>
        <groupId>net.minidev</groupId>
        <artifactId>json-smart</artifactId>
        <version>2.5.2</version>
      </dependency>""",
        ).replace(
            dependency_anchor,
            dependency_anchor
            + """
    <dependency>
      <groupId>org.apache.calcite</groupId>
      <artifactId>calcite-core</artifactId>
      <version>1.41.0</version>
    </dependency>""",
        )
        completed = self._run_effective_pom_parser(non_pilot_versions)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_profile_off_effective_pom_rejects_only_routecontract_activation_leaks(
        self,
    ) -> None:
        management_anchor = """\
      <dependency>
        <groupId>example</groupId>
        <artifactId>production-bom</artifactId>
        <version>1.0.0</version>
      </dependency>"""
        dependency_anchor = """\
    <dependency>
      <groupId>com.mysql</groupId>
      <artifactId>mysql-connector-j</artifactId>
      <version>8.4.0</version>
    </dependency>"""
        source_anchor = "<sources><source>src/generated/java</source></sources>"
        mutations = {
            "global Jackson BOM": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                management_anchor,
                management_anchor
                + """
      <dependency>
        <groupId>com.fasterxml.jackson</groupId>
        <artifactId>jackson-bom</artifactId>
        <version>2.18.9</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>""",
            ),
            "global Calcite management": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                management_anchor,
                management_anchor
                + """
      <dependency>
        <groupId>org.apache.calcite</groupId>
        <artifactId>calcite-linq4j</artifactId>
        <version>1.42.0</version>
      </dependency>""",
            ),
            "global minidev management": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                management_anchor,
                management_anchor
                + """
      <dependency>
        <groupId>net.minidev</groupId>
        <artifactId>json-smart</artifactId>
        <version>2.4.10</version>
      </dependency>""",
            ),
            "direct RouteContract": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                dependency_anchor,
                dependency_anchor
                + """
    <dependency>
      <groupId>io.github.ym0506.routecontract</groupId>
      <artifactId>routecontract-shardingsphere-5.5</artifactId>
      <version>0.1.2</version>
    </dependency>""",
            ),
            "other direct RouteContract artifact": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                dependency_anchor,
                dependency_anchor
                + """
    <dependency>
      <groupId>io.github.ym0506.routecontract</groupId>
      <artifactId>routecontract-future-adapter</artifactId>
      <version>9.9.9</version>
    </dependency>""",
            ),
            "direct Calcite": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                dependency_anchor,
                dependency_anchor
                + """
    <dependency>
      <groupId>org.apache.calcite</groupId>
      <artifactId>calcite-core</artifactId>
      <version>1.42.0</version>
    </dependency>""",
            ),
            "ShardingSphere pilot exclusion": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                """\
        <exclusion>
          <groupId>example</groupId>
          <artifactId>unrelated-production-exclusion</artifactId>
        </exclusion>""",
                """\
        <exclusion>
          <groupId>org.locationtech.jts.io</groupId>
          <artifactId>jts-io-common</artifactId>
        </exclusion>""",
            ),
            "MySQL pilot exclusion": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                "<version>8.4.0</version>",
                """\
<version>8.4.0</version>
      <exclusions>
        <exclusion>
          <groupId>com.google.protobuf</groupId>
          <artifactId>protobuf-java</artifactId>
        </exclusion>
      </exclusions>""",
            ),
            "RouteContract repository": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                "production-repository",
                "routecontract-verified-file-repository",
            ),
            "relative pilot source": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                source_anchor,
                "<sources><source>src/routeContractPilot/java</source></sources>",
            ),
            "absolute pilot source": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                source_anchor,
                "<sources><source>/work/src/routeContractPilot/java/</source></sources>",
            ),
            "missing MySQL base": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                dependency_anchor, ""
            ),
            "duplicate ShardingSphere base": VALID_PROFILE_OFF_EFFECTIVE_POM.replace(
                dependency_anchor,
                dependency_anchor
                + """
    <dependency>
      <groupId>org.apache.shardingsphere</groupId>
      <artifactId>shardingsphere-jdbc</artifactId>
      <version>5.5.3</version>
    </dependency>""",
            ),
        }
        rejected = {
            "direct RouteContract",
            "other direct RouteContract artifact",
            "RouteContract repository",
            "relative pilot source",
            "absolute pilot source",
        }
        for name, effective_pom in mutations.items():
            with self.subTest(name=name):
                completed = self._run_effective_pom_parser(effective_pom)
                if name in rejected:
                    self.assertNotEqual(0, completed.returncode)
                else:
                    self.assertEqual(0, completed.returncode, completed.stderr)

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
                "routecontract-shardingsphere-5.5:jar:0.1.2:test",
                "routecontract-shardingsphere-5.5:jar:0.1.2:compile",
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
        self.assertEqual(5, script.count("-Dmaven.test.failure.ignore=false"))
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

        for element in (
            "rerunFailure",
            "rerunError",
            "flakyFailure",
            "flakyError",
        ):
            with self.subTest(element=element):
                retry_suite = passing.replace(
                    "/>", f"><{element}/></testcase>", 1
                )
                completed = self._run_profile_parser(retry_suite)
                self.assertNotEqual(0, completed.returncode)
                self.assertIn("retry evidence", completed.stderr)


if __name__ == "__main__":
    unittest.main()
