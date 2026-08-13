#!/usr/bin/env python3
"""Adversarial integration tests for the final supply-chain scan runner."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "scripts" / "run-final-supply-chain-scan.sh"
POLICY = REPOSITORY_ROOT / "security" / "supply-chain-policy.json"

GENERATED_INPUTS = (
    "build/reports/verified-sbom/aggregate/bom.json",
    "build/reports/verified-sbom/aggregate/bom.xml",
    "build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.json",
    "build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.xml",
    "build/reports/verified-sbom/mysql-example/bom.json",
    "build/reports/verified-sbom/mysql-example/bom.xml",
    "routecontract-shardingsphere-5.5/build/publications/mavenJava/pom-default.xml",
)
RAW_SCAN = "build/reports/security/osv-raw.json"
EVIDENCE = "build/reports/security/supply-chain-evidence.json"
KNOWN_FINDING = "GHSA-TEST-UNSUPPRESSED"
SCANNER_COMMIT = "a" * 40
SCANNER_VERSION = "2.5.0-test"
SCALIBR_VERSION = "0.4.5-test"
DATABASE_BYTES = b"pinned fake Maven vulnerability database\n"

FAKE_GRADLE = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$@" > "${TEST_GRADLE_LOG:?}"
if [[ "${TEST_GRADLE_MODE:-success}" == "fail" ]]; then
  exit 77
fi
while IFS= read -r generated_input; do
  if [[ "${TEST_GRADLE_SKIP:-}" == "${generated_input}" ]]; then
    continue
  fi
  mkdir -p "$(dirname "${generated_input}")"
  if [[ "${TEST_GRADLE_SYMLINK:-}" == "${generated_input}" ]]; then
    ln -s "${TEST_SYMLINK_TARGET:?}" "${generated_input}"
  else
    printf 'fresh:%s\\n' "${generated_input}" > "${generated_input}"
  fi
done <<'EOF'
build/reports/verified-sbom/aggregate/bom.json
build/reports/verified-sbom/aggregate/bom.xml
build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.json
build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.xml
build/reports/verified-sbom/mysql-example/bom.json
build/reports/verified-sbom/mysql-example/bom.xml
routecontract-shardingsphere-5.5/build/publications/mavenJava/pom-default.xml
EOF
if [[ "${TEST_GRADLE_MUTATE_TRACKED:-0}" == "1" ]]; then
  printf 'mutated by fake Gradle\\n' >> tracked-marker.txt
fi
"""

FAKE_CHECKER = f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys


def option(name):
    index = sys.argv.index(name)
    return Path(sys.argv[index + 1])


with Path(os.environ["TEST_CHECKER_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")

command = sys.argv[1]
if command == "preflight":
    json.loads(option("--scanner-lock").read_text(encoding="utf-8"))
    json.loads(option("--policy").read_text(encoding="utf-8"))
    if option("--scanner-config").read_bytes() != b"":
        raise SystemExit("fake checker: explicit scanner config is not empty")
elif command == "inventory":
    for flag in (
        "--sbom", "--sbom-xml", "--published-sbom", "--published-sbom-xml",
        "--example-sbom", "--example-sbom-xml", "--published-pom",
        "--published-lock",
    ):
        if not option(flag).is_file():
            raise SystemExit(f"fake checker: missing {{flag}}")
    option("--output").write_text("fixture:1.0=fake\\nempty=\\n", encoding="utf-8")
elif command == "verify":
    raw = json.loads(option("--raw-scan").read_text(encoding="utf-8"))
    finding = raw["results"][0]["packages"][0]["vulnerabilities"][0]["id"]
    if finding != "{KNOWN_FINDING}":
        raise SystemExit("fake checker: known finding was suppressed")
    option("--output").write_text(
        json.dumps({{"knownUnsuppressedFinding": finding}}, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
else:
    raise SystemExit(f"fake checker: unexpected command {{command}}")
"""

FAKE_SCANNER = f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1:-}}" == "--version" ]]; then
  printf '%s\\n' \\
    'osv-scanner version: {SCANNER_VERSION}' \\
    'osv-scalibr version: {SCALIBR_VERSION}' \\
    'commit: {SCANNER_COMMIT}'
  exit 0
fi

printf '%s\\n' "$@" > "${{TEST_SCANNER_LOG:?}}"
config_count=0
config_path=''
output_path=''
lockfile_path=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      config_count=$((config_count + 1))
      config_path="$2"
      shift 2
      ;;
    --output-file)
      output_path="$2"
      shift 2
      ;;
    --lockfile)
      lockfile_path="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

repository_root="$(git rev-parse --show-toplevel)"
[[ "${{config_count}}" -eq 1 ]] || exit 81
[[ "${{config_path}}" == "${{repository_root}}/security/osv-scanner.toml" ]] || exit 82
[[ -f "${{config_path}}" && ! -L "${{config_path}}" && ! -s "${{config_path}}" ]] || exit 83
git ls-files --error-unmatch -- security/osv-scanner.toml >/dev/null || exit 84
adjacent_config="$(dirname "${{lockfile_path}}")/osv-scanner.toml"
grep -Fq '{KNOWN_FINDING}' "${{adjacent_config}}" || exit 85

case "${{TEST_AROUND_USE_MUTATION:-none}}" in
  scanner)
    printf '\\n' >> "$0"
    ;;
  database)
    printf '\\n' >> "${{OSV_SCALIBR_LOCAL_DB_CACHE_DIRECTORY}}/osv-scalibr/Maven/all.zip"
    ;;
  config)
    printf '# mutation during scanner use\\n' >> "${{config_path}}"
    ;;
  generated)
    printf '\\nmutation during scanner use\\n' \\
      >> "${{repository_root}}/${{TEST_MUTATION_PATH:?}}"
    ;;
  audited)
    audited_path="$(find "${{repository_root}}/build/reports/security/derived" \\
      -path '*/audited-inputs.*/aggregate-bom.json' -print -quit)"
    [[ -n "${{audited_path}}" ]] || exit 87
    chmod 0600 "${{audited_path}}"
    printf '\\nmutation during scanner use\\n' >> "${{audited_path}}"
    ;;
  inventory)
    chmod 0600 "${{lockfile_path}}"
    printf '\\nmutation during scanner use\\n' >> "${{lockfile_path}}"
    ;;
  none)
    ;;
  *)
    exit 86
    ;;
esac

printf '%s\\n' \\
  '{{"results":[{{"source":{{"type":"lockfile"}},"packages":[{{"package":{{"name":"example:known","version":"1.0","ecosystem":"Maven"}},"vulnerabilities":[{{"id":"{KNOWN_FINDING}"}}]}}]}}]}}' \\
  > "${{output_path}}"
exit 1
"""


class FinalSupplyChainRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.repository = self.root / "repository"
        (self.repository / "scripts").mkdir(parents=True)
        (self.repository / "security").mkdir()

        shutil.copy2(RUNNER, self.repository / "scripts" / RUNNER.name)
        shutil.copy2(POLICY, self.repository / "security" / POLICY.name)
        (self.repository / "scripts" / "verify-supply-chain-policy.py").write_text(
            FAKE_CHECKER, encoding="utf-8"
        )
        (self.repository / "security" / "osv-scanner.toml").write_bytes(b"")
        (self.repository / ".gitignore").write_text(
            "/build/\n**/build/\n", encoding="utf-8"
        )
        (self.repository / "tracked-marker.txt").write_text(
            "original tracked content\n", encoding="utf-8"
        )
        published_module = self.repository / "routecontract-shardingsphere-5.5"
        published_module.mkdir()
        (published_module / "gradle.lockfile").write_text(
            "fixture:1.0=compileClasspath,runtimeClasspath\n"
            "empty=annotationProcessor,testAnnotationProcessor\n",
            encoding="utf-8",
        )
        gradle_wrapper = self.repository / "gradlew"
        gradle_wrapper.write_text(FAKE_GRADLE, encoding="utf-8")
        gradle_wrapper.chmod(0o755)

        self.scanner_bytes = FAKE_SCANNER.encode("utf-8")
        self.scanner_sha = hashlib.sha256(self.scanner_bytes).hexdigest()
        self.database_sha = hashlib.sha256(DATABASE_BYTES).hexdigest()
        self.platform_name = {
            ("Darwin", "arm64"): "darwin-arm64",
            ("Linux", "x86_64"): "linux-x86_64",
        }.get((platform.system(), platform.machine()))
        self.lock_document = self.make_lock()
        self.write_lock()

        self.git("init", "-b", "main")
        self.git("config", "user.name", "Supply Chain Runner Test")
        self.git("config", "user.email", "runner-test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        self.revision = self.git("rev-parse", "HEAD").stdout.strip()

        self.gradle_log = self.root / "gradle-arguments.txt"
        self.scanner_log = self.root / "scanner-arguments.txt"
        self.checker_log = self.root / "checker-arguments.jsonl"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_lock(self) -> dict[str, object]:
        platform_asset = {
            "sha256": self.scanner_sha,
            "size": len(self.scanner_bytes),
            "url": "https://example.invalid/osv-scanner",
        }
        return {
            "schemaVersion": 1,
            "scanner": {
                "name": "OSV-Scanner",
                "version": SCANNER_VERSION,
                "commit": SCANNER_COMMIT,
                "scalibrVersion": SCALIBR_VERSION,
                "platforms": {
                    "darwin-arm64": dict(platform_asset),
                    "linux-x86_64": dict(platform_asset),
                },
            },
            "database": {
                "ecosystem": "Maven",
                "generation": "1786244630000000",
                "lastModified": "2026-08-09T03:03:50.782Z",
                "sha256": self.database_sha,
                "size": len(DATABASE_BYTES),
                "url": (
                    "https://example.invalid/Maven/"
                    "all.zip?generation=1786244630000000"
                ),
            },
        }

    def write_lock(self) -> None:
        (self.repository / "security" / "osv-scanner.lock.json").write_text(
            json.dumps(self.lock_document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def commit_lock(self, message: str) -> None:
        self.write_lock()
        self.git("add", "security/osv-scanner.lock.json")
        self.git("commit", "-m", message)
        self.revision = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def run_runner(
        self, extra_environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        for log in (self.gradle_log, self.scanner_log, self.checker_log):
            log.unlink(missing_ok=True)
        environment = os.environ.copy()
        environment.update(
            {
                "TEST_GRADLE_LOG": str(self.gradle_log),
                "TEST_SCANNER_LOG": str(self.scanner_log),
                "TEST_CHECKER_LOG": str(self.checker_log),
            }
        )
        environment.update(extra_environment or {})
        return subprocess.run(
            [
                "bash",
                str(self.repository / "scripts" / RUNNER.name),
                "--revision",
                self.revision,
            ],
            cwd=self.repository,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )

    def require_supported_platform(self) -> str:
        if self.platform_name is None:
            self.skipTest(
                f"runner does not support {(platform.system(), platform.machine())}"
            )
        return self.platform_name

    def install_valid_caches(self) -> tuple[Path, Path]:
        platform_name = self.require_supported_platform()
        tool_directory = self.repository / "build/security-tools/final-scan"
        tool_directory.mkdir(parents=True, exist_ok=True)
        scanner = tool_directory / f"osv-scanner-{platform_name}-{self.scanner_sha}"
        scanner.write_bytes(self.scanner_bytes)
        scanner.chmod(0o755)
        database = (
            tool_directory
            / f"database-{self.database_sha}/osv-scalibr/Maven/all.zip"
        )
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_bytes(DATABASE_BYTES)
        return scanner, database

    def install_adjacent_ignored_config(self) -> Path:
        adjacent = (
            self.repository
            / "build/reports/security/derived/osv-scanner.toml"
        )
        adjacent.parent.mkdir(parents=True, exist_ok=True)
        adjacent.write_text(
            f'[[IgnoredVulns]]\nid = "{KNOWN_FINDING}"\n', encoding="utf-8"
        )
        return adjacent

    def generated_path(self, relative: str) -> Path:
        return self.repository / relative

    def write_stale_generated_inputs(self) -> None:
        for relative in GENERATED_INPUTS:
            path = self.generated_path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"stale:{relative}\n", encoding="utf-8")

    def clear_generated_inputs(self) -> None:
        for relative in GENERATED_INPUTS:
            path = self.generated_path(relative)
            if path.is_symlink() or path.is_file():
                path.unlink()

    def prepare_successful_pipeline(self) -> None:
        self.install_valid_caches()
        self.install_adjacent_ignored_config()

    def assert_no_final_output(self) -> None:
        self.assertFalse(self.generated_path(RAW_SCAN).exists())
        self.assertFalse(self.generated_path(EVIDENCE).exists())

    def test_fixture_uses_production_build_ignores_and_non_destructive_gradle(self) -> None:
        self.assertEqual(
            "/build/\n**/build/\n",
            (self.repository / ".gitignore").read_text(encoding="utf-8"),
        )
        root_probe = self.repository / "build/root-probe.txt"
        nested_probe = self.repository / "module/build/nested-probe.txt"
        root_probe.parent.mkdir(parents=True)
        nested_probe.parent.mkdir(parents=True)
        root_probe.write_text("ignored\n", encoding="utf-8")
        nested_probe.write_text("ignored\n", encoding="utf-8")
        ignored = self.git(
            "check-ignore", "build/root-probe.txt", "module/build/nested-probe.txt"
        ).stdout.splitlines()

        self.assertEqual(
            ["build/root-probe.txt", "module/build/nested-probe.txt"], ignored
        )
        wrapper = (self.repository / "gradlew").read_text(encoding="utf-8")
        self.assertNotIn("rm -rf", wrapper)
        self.assertNotIn("rm ", wrapper)
        self.assertNotIn(" clean ", f" {wrapper} ")

    def test_rejects_untracked_and_tracked_worktree_content(self) -> None:
        (self.repository / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
        untracked = self.run_runner()
        self.assertNotEqual(0, untracked.returncode)
        self.assertIn("worktree is dirty", untracked.stderr)
        (self.repository / "unexpected.txt").unlink()

        (self.repository / "tracked-marker.txt").write_text(
            "dirty tracked content\n", encoding="utf-8"
        )
        tracked = self.run_runner()
        self.assertNotEqual(0, tracked.returncode)
        self.assertIn("worktree is dirty", tracked.stderr)

    def test_rejects_untracked_symlink_build_root_without_writing_outside(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        os.symlink(outside, self.repository / "build")

        result = self.run_runner()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("worktree is dirty", result.stderr)
        self.assertEqual([], list(outside.iterdir()))
        self.assertFalse(self.gradle_log.exists())

    def test_rejects_symlink_scanner_cache_directory(self) -> None:
        security_tools = self.repository / "build/security-tools"
        security_tools.mkdir(parents=True)
        victim = self.root / "victim-directory"
        victim.mkdir()
        os.symlink(victim, security_tools / "final-scan")

        result = self.run_runner()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("symbolic link", result.stderr)
        self.assertEqual([], list(victim.iterdir()))

    def test_preexisting_final_outputs_fail_before_gradle_and_preserve_bytes(self) -> None:
        for relative in (RAW_SCAN, EVIDENCE):
            with self.subTest(output=relative):
                path = self.generated_path(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                original = f"preserve:{relative}\n".encode("utf-8")
                path.write_bytes(original)

                result = self.run_runner()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("prior final scan output exists", result.stderr)
                self.assertEqual(original, path.read_bytes())
                self.assertFalse(self.gradle_log.exists())
                path.unlink()

    def test_preexisting_final_output_symlinks_fail_before_gradle_and_preserve_target(self) -> None:
        victim = self.root / "final-output-victim.bin"
        original = b"preserve final output symlink target\x00\xff"
        victim.write_bytes(original)
        for relative in (RAW_SCAN, EVIDENCE):
            with self.subTest(output_symlink=relative):
                path = self.generated_path(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(victim, path)

                result = self.run_runner()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("prior final scan output exists", result.stderr)
                self.assertTrue(path.is_symlink())
                self.assertEqual(original, victim.read_bytes())
                self.assertFalse(self.gradle_log.exists())
                path.unlink()

    def test_regenerates_all_seven_inputs_without_cleaning_unrelated_build_files(self) -> None:
        self.write_stale_generated_inputs()
        root_sentinel = self.repository / "build/unrelated/root-sentinel.bin"
        module_sentinel = (
            self.repository
            / "routecontract-shardingsphere-5.5/build/unrelated/module-sentinel.bin"
        )
        root_sentinel.parent.mkdir(parents=True, exist_ok=True)
        module_sentinel.parent.mkdir(parents=True, exist_ok=True)
        root_sentinel.write_bytes(b"preserve root build bytes\x00\xff")
        module_sentinel.write_bytes(b"preserve module build bytes\x00\xfe")
        self.prepare_successful_pipeline()

        result = self.run_runner()

        self.assertEqual(0, result.returncode, result.stderr)
        for relative in GENERATED_INPUTS:
            self.assertEqual(
                f"fresh:{relative}\n",
                self.generated_path(relative).read_text(encoding="utf-8"),
            )
        self.assertEqual(b"preserve root build bytes\x00\xff", root_sentinel.read_bytes())
        self.assertEqual(
            b"preserve module build bytes\x00\xfe", module_sentinel.read_bytes()
        )
        arguments = self.gradle_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [
                "--no-daemon",
                "--no-build-cache",
                "--rerun-tasks",
                "prepareVerifiedSbom",
                ":routecontract-shardingsphere-5.5:generatePomFileForMavenJavaPublication",
            ],
            arguments,
        )
        self.assertNotIn("clean", arguments)

    def test_generation_failure_stops_before_scanner_and_preserves_sentinel(self) -> None:
        self.write_stale_generated_inputs()
        sentinel = self.repository / "build/unrelated/sentinel.txt"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("preserve me\n", encoding="utf-8")

        result = self.run_runner({"TEST_GRADLE_MODE": "fail"})

        self.assertEqual(77, result.returncode)
        self.assertTrue(self.gradle_log.exists())
        self.assertFalse(self.scanner_log.exists())
        self.assertEqual("preserve me\n", sentinel.read_text(encoding="utf-8"))
        for relative in GENERATED_INPUTS:
            self.assertFalse(self.generated_path(relative).exists())
        self.assert_no_final_output()

    def test_rejects_each_missing_generated_input(self) -> None:
        for relative in GENERATED_INPUTS:
            with self.subTest(missing=relative):
                result = self.run_runner({"TEST_GRADLE_SKIP": relative})

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    f"required input is not a regular non-symlink file: {relative}",
                    result.stderr,
                )
                self.assertFalse(self.scanner_log.exists())
                self.assert_no_final_output()

    def test_rejects_each_prior_generated_input_symlink_before_gradle(self) -> None:
        victim = self.root / "prior-generated-victim.bin"
        victim.write_bytes(b"do not touch prior victim")
        for relative in GENERATED_INPUTS:
            with self.subTest(prior_symlink=relative):
                self.clear_generated_inputs()
                path = self.generated_path(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(victim, path)

                result = self.run_runner()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("symbolic link", result.stderr)
                self.assertFalse(self.gradle_log.exists())
                self.assertEqual(b"do not touch prior victim", victim.read_bytes())
                path.unlink()

    def test_rejects_each_generated_input_symlink_after_gradle(self) -> None:
        victim = self.root / "new-generated-victim.bin"
        victim.write_bytes(b"do not touch generated victim")
        for relative in GENERATED_INPUTS:
            with self.subTest(generated_symlink=relative):
                self.clear_generated_inputs()

                result = self.run_runner(
                    {
                        "TEST_GRADLE_SYMLINK": relative,
                        "TEST_SYMLINK_TARGET": str(victim),
                    }
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("symbolic link", result.stderr)
                self.assertTrue(self.gradle_log.exists())
                self.assertFalse(self.scanner_log.exists())
                self.assertEqual(b"do not touch generated victim", victim.read_bytes())

    def test_rejects_tracked_mutation_after_generation(self) -> None:
        result = self.run_runner({"TEST_GRADLE_MUTATE_TRACKED": "1"})

        self.assertNotEqual(0, result.returncode)
        self.assertIn("worktree is dirty", result.stderr)
        self.assertIn(
            "mutated by fake Gradle",
            (self.repository / "tracked-marker.txt").read_text(encoding="utf-8"),
        )
        self.assertFalse(self.scanner_log.exists())
        self.assert_no_final_output()

    def test_successful_fake_pipeline_uses_only_absolute_tracked_empty_config(self) -> None:
        adjacent = self.install_adjacent_ignored_config()
        self.install_valid_caches()

        result = self.run_runner()

        self.assertEqual(0, result.returncode, result.stderr)
        scanner_arguments = self.scanner_log.read_text(encoding="utf-8").splitlines()
        config_indexes = [
            index for index, value in enumerate(scanner_arguments) if value == "--config"
        ]
        self.assertEqual(1, len(config_indexes))
        config_path = Path(scanner_arguments[config_indexes[0] + 1])
        self.assertTrue(config_path.is_absolute())
        self.assertEqual(
            self.repository / "security/osv-scanner.toml", config_path
        )
        self.assertEqual(b"", config_path.read_bytes())
        self.assertEqual(
            "security/osv-scanner.toml",
            self.git("ls-files", "security/osv-scanner.toml").stdout.strip(),
        )
        self.assertIn(KNOWN_FINDING, adjacent.read_text(encoding="utf-8"))
        raw = json.loads(self.generated_path(RAW_SCAN).read_text(encoding="utf-8"))
        self.assertEqual(
            KNOWN_FINDING,
            raw["results"][0]["packages"][0]["vulnerabilities"][0]["id"],
        )
        evidence = json.loads(
            self.generated_path(EVIDENCE).read_text(encoding="utf-8")
        )
        self.assertEqual(KNOWN_FINDING, evidence["knownUnsuppressedFinding"])
        self.assertIn("sanitized supply-chain evidence", result.stdout)
        checker_calls = [
            json.loads(line)
            for line in self.checker_log.read_text(encoding="utf-8").splitlines()
        ]
        verify_call = next(call for call in checker_calls if call[0] == "verify")
        self.assertEqual(
            self.revision, verify_call[verify_call.index("--revision") + 1]
        )
        source_tree = verify_call[verify_call.index("--source-tree") + 1]
        self.assertRegex(source_tree, r"^[0-9a-f]{40}$")
        status = self.git(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ).stdout
        self.assertEqual("", status)

    def test_rejects_cached_scanner_and_database_with_wrong_size(self) -> None:
        original_lock = copy.deepcopy(self.lock_document)
        for label in ("scanner", "database"):
            with self.subTest(cache=label):
                self.lock_document = copy.deepcopy(original_lock)
                if label == "scanner":
                    for asset in self.lock_document["scanner"]["platforms"].values():
                        asset["size"] = len(self.scanner_bytes) + 1
                else:
                    self.lock_document["database"]["size"] = len(DATABASE_BYTES) + 1
                self.commit_lock(f"wrong cached {label} size")
                shutil.rmtree(
                    self.repository / "build/security-tools", ignore_errors=True
                )
                self.install_valid_caches()

                result = self.run_runner()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("cached file size mismatch", result.stderr)
                self.assert_no_final_output()

    def run_around_use_mutation(self, target: str) -> subprocess.CompletedProcess[str]:
        self.prepare_successful_pipeline()
        return self.run_runner({"TEST_AROUND_USE_MUTATION": target})

    def test_rejects_scanner_binary_mutation_during_use(self) -> None:
        result = self.run_around_use_mutation("scanner")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("scanner binary size changed", result.stderr)
        self.assert_no_final_output()

    def test_rejects_database_mutation_during_scanner_use(self) -> None:
        result = self.run_around_use_mutation("database")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("scanner database size changed", result.stderr)
        self.assert_no_final_output()

    def test_rejects_tracked_empty_config_mutation_during_scanner_use(self) -> None:
        result = self.run_around_use_mutation("config")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("explicit scanner config is not empty", result.stderr)
        self.assertNotEqual(
            b"", (self.repository / "security/osv-scanner.toml").read_bytes()
        )
        self.assert_no_final_output()

    def test_rejects_each_generated_input_mutation_during_scanner_use(self) -> None:
        for relative in GENERATED_INPUTS:
            with self.subTest(generated_input=relative):
                self.prepare_successful_pipeline()
                result = self.run_runner(
                    {
                        "TEST_AROUND_USE_MUTATION": "generated",
                        "TEST_MUTATION_PATH": relative,
                    }
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("audited scan input changed", result.stderr)
                self.assert_no_final_output()

    def test_rejects_private_audited_copy_mutation_during_scanner_use(self) -> None:
        result = self.run_around_use_mutation("audited")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("audited scan input changed", result.stderr)
        self.assert_no_final_output()

    def test_rejects_derived_inventory_mutation_during_scanner_use(self) -> None:
        result = self.run_around_use_mutation("inventory")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("audited scan input changed", result.stderr)
        self.assert_no_final_output()


if __name__ == "__main__":
    unittest.main()
