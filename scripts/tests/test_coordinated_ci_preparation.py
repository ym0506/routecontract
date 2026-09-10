"""CI wiring regressions; synthetic context fixtures are not release evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/ci.yml'
SELECT = 'Select stable coordinated CI preparation'
SCAN = 'Scan exact source for coordinated CI preparation'
PREPARE = 'Collect and verify coordinated unsigned CI preparation'
UPLOAD = 'Upload coordinated unsigned CI preparation'
GUARD = "if: steps.coordinated_ci_version.outputs.enabled == 'true'"


def step(name, workflow=WORKFLOW):
    text = workflow.read_text()
    pattern = r'^      - name: ' + re.escape(name) + r'\n.*?(?=^      - name: |^  [a-z][a-z0-9-]*:|\Z)'
    matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise AssertionError('Expected exactly one CI step: ' + name)
    return matches[0]


def inline_python(name):
    block = step(name)
    match = re.search(r"          python3 - <<'PY'\n(.*?)^          PY$", block, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError('Expected the actual inline Python in ' + name)
    return '\n'.join(line.removeprefix('          ') for line in match[1].splitlines()) + '\n'


class CoordinatedCiPreparationTest(unittest.TestCase):
    def test_selector_only_enables_literal_stable_02_versions(self):
        script = inline_python(SELECT)
        for version, enabled in [('0.2.0', True), ('0.2.19', True), ('0.1.3', False),
                                 ('0.2.0-SNAPSHOT', False), ('0.2.0-rc1', False),
                                 ('0.2.01', False), ('0.3.0', False)]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                (root / 'build.gradle').write_text("version = '" + version + "'\n")
                output = root / 'step-output'
                result = subprocess.run([sys.executable, '-c', script], cwd=root,
                                        env=dict(os.environ, GITHUB_OUTPUT=str(output)), capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual('enabled=true\nversion=' + version + '\n' if enabled else 'enabled=false\n',
                                 output.read_text())

    def test_selector_rejects_ambiguous_or_missing_source_version(self):
        script = inline_python(SELECT)
        for build in ("version = '0.2.0'\nversion = '0.1.3'\n", '// no version\n'):
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                (root / 'build.gradle').write_text(build)
                output = root / 'step-output'
                result = subprocess.run([sys.executable, '-c', script], cwd=root,
                                        env=dict(os.environ, GITHUB_OUTPUT=str(output)), capture_output=True)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(output.exists())

    def test_existing_root_build_and_strict_summary_precede_preparation(self):
        text = WORKFLOW.read_text()
        names = ['Test, assemble artifacts, and validate all CycloneDX SBOMs',
                 'Verify complete core, adapter and MySQL result coverage', SELECT, SCAN, PREPARE, UPLOAD,
                 'Verify printed Gradle and Maven installation configuration',
                 'Smoke-test local Maven Central staging and signing']
        indices = [text.index('      - name: ' + name + '\n') for name in names]
        self.assertEqual(sorted(indices), indices)
        self.assertLess(indices[-1], text.index('  maven-java21-pilot:'))
        for name in (SCAN, PREPARE):
            self.assertIn(GUARD, step(name))
            self.assertIn('set -euo pipefail', step(name))
            self.assertNotIn('continue-on-error', step(name))

    def test_scan_and_staging_bind_actual_checkout_not_signing_smoke_archive(self):
        scan = step(SCAN)
        self.assertIn('git rev-parse --verify HEAD', scan)
        self.assertIn('git status --porcelain=v1 --untracked-files=all --ignore-submodules=none', scan)
        self.assertIn('./scripts/run-final-supply-chain-scan.sh --revision "${GITHUB_SHA}"', scan)
        prepare = step(PREPARE)
        self.assertIn('publishRouteContractCentralStaging', prepare)
        self.assertIn('-ProutecontractCentralSigning=false', prepare)
        self.assertIn('--source-root "$PWD"', prepare)
        self.assertEqual(2, prepare.count('--revision "${GITHUB_SHA}"'))
        self.assertIn('--java-home "${JAVA_HOME}"', prepare)
        self.assertLess(prepare.index('publishRouteContractCentralStaging'),
                        prepare.index('prepare-coordinated-release-evidence.py collect'))
        self.assertLess(prepare.index('prepare-coordinated-release-evidence.py collect'),
                        prepare.index('prepare-coordinated-release-evidence.py verify'))
        for forbidden in ('routecontract-central-smoke', 'set_version', 'git archive', 'git checkout',
                          'Signing=true', 'signing.gnupg', 'verify-staged-', 'clean check', 'secrets.'):
            self.assertNotIn(forbidden, scan + prepare)

    def test_staging_creates_private_absent_parent_without_changing_runner_temp(self):
        paths = [(WORKFLOW, PREPARE, 'routecontract-coordinated-ci-staging'),
                 (ROOT / '.github/workflows/release-evidence.yml',
                  'Collect and validate coordinated unsigned split preparation', 'routecontract-release-staging')]
        for workflow, name, directory in paths:
            with self.subTest(workflow=workflow.name), tempfile.TemporaryDirectory() as raw:
                run = step(name, workflow).split('        run: |\n', 1)[1]
                prefix = '\n'.join(line.removeprefix('          ') for line in run.splitlines()).split('./gradlew', 1)[0]
                root = Path(raw)
                ambient = root / 'runner-temp'
                ambient.mkdir(mode=0o755)
                ambient.chmod(0o755)
                environment = dict(os.environ, RUNNER_TEMP=str(ambient))
                result = subprocess.run(['bash', '-c', prefix], cwd=root, env=environment, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                parent = ambient / directory
                self.assertTrue(parent.is_dir())
                self.assertEqual(0o700, parent.stat().st_mode & 0o777)
                self.assertEqual(0o755, ambient.stat().st_mode & 0o777)
                self.assertFalse((parent / 'repository').exists())
                repeated = subprocess.run(['bash', '-c', prefix], cwd=root, env=environment, capture_output=True)
                self.assertNotEqual(0, repeated.returncode)

    def context(self, event_name='pull_request', candidate_revision='a' * 40):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        target = root / 'build/coordinated-ci-preparation'
        target.mkdir(parents=True)
        manifest = target / 'candidate-payloads.json'
        manifest.write_text(json.dumps({'sourceRevision': candidate_revision, 'sourceTree': 'c' * 40,
                                       'reviewed': False, 'signed': False, 'published': False,
                                       'publicationHeld': True}))
        event = root / 'event.json'
        event.write_text(json.dumps({'pull_request': {'head': {'sha': 'b' * 40}}}))
        result = subprocess.run([sys.executable, '-c', inline_python(PREPARE)], cwd=root,
                                env=dict(os.environ, GITHUB_SHA='a' * 40, GITHUB_EVENT_NAME=event_name,
                                         GITHUB_EVENT_PATH=str(event), GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1'),
                                capture_output=True, text=True)
        return root, manifest, result

    def test_context_distinguishes_pr_merge_from_head_and_preserves_hold(self):
        root, manifest, result = self.context()
        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads((root / 'build/ci-evidence/coordinated-preparation-context.json').read_text())
        self.assertEqual('a' * 40, context['testedRevision'])
        self.assertEqual('b' * 40, context['pullRequestHeadRevision'])
        self.assertEqual('pull-request-merge', context['testedRevisionRole'])
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), context['candidateManifestSha256'])
        self.assertTrue(context['publicationHeld'])
        self.assertFalse(context['signed'])
        self.assertFalse(context['published'])
        self.assertFalse(context['reviewed'])
        self.assertIsNone(context['humanReview'])
        self.assertEqual(['candidate-payloads.json'], [p.name for p in manifest.parent.iterdir()])

    def test_context_cannot_relabel_candidate_revision_or_invent_pr_for_push(self):
        root, _, result = self.context(candidate_revision='d' * 40)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((root / 'build/ci-evidence/coordinated-preparation-context.json').exists())
        root, _, result = self.context(event_name='push')
        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads((root / 'build/ci-evidence/coordinated-preparation-context.json').read_text())
        self.assertEqual('checked-out-commit', context['testedRevisionRole'])
        self.assertIsNone(context['pullRequestHeadRevision'])

    def test_only_verified_closed_candidate_is_uploaded_and_release_hold_remains(self):
        prepare = step(PREPARE)
        self.assertLess(prepare.index('prepare-coordinated-release-evidence.py verify'),
                        prepare.index("echo 'available=true'"))
        upload = step(UPLOAD)
        self.assertIn("if: steps.coordinated_ci_candidate.outputs.available == 'true'", upload)
        self.assertIn('path: build/coordinated-ci-preparation/', upload)
        self.assertIn('name: routecontract-coordinated-ci-preparation-${{ github.sha }}', upload)
        self.assertIn('if-no-files-found: error', upload)
        self.assertNotIn('always()', upload)
        self.assertNotIn('osv-raw', upload)
        self.assertIn('build/ci-evidence/coordinated-preparation-context.json', step('Upload test and environment evidence'))
        release = (ROOT / '.github/workflows/release-evidence.yml').read_text()
        self.assertIn('0.2 publication is blocked:', release)
        self.assertIn('exit 1', release[release.index('0.2 publication is blocked:'):])


if __name__ == '__main__':
    unittest.main()
