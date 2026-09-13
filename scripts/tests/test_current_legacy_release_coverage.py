"""The current upgrade plans must cover the newest already published legacy JAR."""
import importlib.util
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import LegacyInputError, load_registry


def helper(filename):
    spec = importlib.util.spec_from_file_location(filename.replace('-', '_'), ROOT / 'scripts' / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


class CurrentPublishedLegacyCoverageTest(unittest.TestCase):
    def current(self):
        return json.loads((ROOT / 'scripts/legacy-artifact-inputs-current.json').read_text())

    def rejects(self, registry):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'registry.json'
            path.write_text(json.dumps(registry))
            with self.assertRaises(LegacyInputError):
                load_registry(path)

    def test_historical_records_remain_identical_in_the_separate_current_registry(self):
        historical = load_registry(ROOT / 'scripts/legacy-artifact-inputs.json')
        current = load_registry(ROOT / 'scripts/legacy-artifact-inputs-current.json')
        self.assertEqual(1, historical['formatVersion'])
        self.assertEqual(2, current['formatVersion'])
        self.assertEqual(historical['distributed'], current['distributed'][:-1])
        self.assertEqual(historical['tagOnly'], current['tagOnly'])
        self.assertEqual('0.1.4', current['distributed'][-1]['version'])

    def test_014_coordinates_and_payload_hashes_match_the_published_receipt(self):
        item = self.current()['distributed'][-1]
        receipt = json.loads((ROOT / 'docs/evidence/release-0.1.4-central/consumer-receipt.json').read_text())
        self.assertEqual('a1eb22087eaf3a49e894d12ba56516efac99343f', item['sourceRevision'])
        self.assertEqual({r['name']: r['sha256'] for r in receipt['artifacts']},
                         {r['name']: r['sha256'] for r in item['payloads']})

    def test_current_format_rejects_missing_duplicate_unreviewed_or_tag_only_versions(self):
        current = self.current()
        missing = copy.deepcopy(current); missing['distributed'].pop()
        duplicate = copy.deepcopy(current); duplicate['distributed'].append(copy.deepcopy(duplicate['distributed'][-1]))
        unknown = copy.deepcopy(current); unknown['distributed'][-1]['version'] = '0.1.5'
        tag_only = copy.deepcopy(current); tag_only['distributed'][-1]['version'] = '0.1.1'
        downgrade = copy.deepcopy(current); downgrade['formatVersion'] = 1
        boolean = copy.deepcopy(current); boolean['formatVersion'] = True
        for variant in (missing, duplicate, unknown, tag_only, downgrade, boolean):
            with self.subTest(versions=[r['version'] for r in variant['distributed']], format=variant['formatVersion']):
                self.rejects(variant)

    def test_014_requires_module_metadata_and_its_exact_public_source(self):
        missing_module = self.current(); missing_module['distributed'][-1]['payloads'].pop()
        wrong_source = self.current()
        wrong_source['distributed'][-1]['payloads'][0]['url'] = 'https://example.org/routecontract-shardingsphere-5.5-0.1.4.jar'
        wrong_version = self.current()
        pin = wrong_version['distributed'][-1]['payloads'][0]
        pin['url'] = pin['url'].replace('/0.1.4/', '/0.1.3/')
        for variant in (missing_module, wrong_source, wrong_version):
            self.rejects(variant)

    def test_current_runners_cannot_silently_downgrade_to_the_historical_registry(self):
        for filename in ('verify-current-entry-successor.py', 'verify-gradle-legacy-artifact-consumer.py',
                         'verify-maven-legacy-artifact-consumer.py'):
            with self.subTest(runner=filename):
                runner = helper(filename)
                with self.assertRaises(LegacyInputError):
                    runner.load_registry(ROOT / 'scripts/legacy-artifact-inputs.json')

    def test_current_entry_plan_includes_installed_014_in_all_twelve_collision_positions(self):
        runner = helper('verify-current-entry-successor.py')
        plan = runner.cases(load_registry(runner.REGISTRY))
        cells = [c for c in plan if c['legacy'] == '0.1.4']
        self.assertEqual(12, len(cells), 'The public 0.1.4 JAR is missing from upgrade collision coverage')
        self.assertEqual(76, len(plan))
        self.assertEqual({(runtime, order, mode) for runtime in ('5.5.2', '5.5.3')
                          for order in ('legacy-first', 'legacy-last')
                          for mode in ('current-capture', 'current-capture-result', 'sql')},
                         {(c['runtime'], c['order'], c['mode']) for c in cells})

    def test_gradle_current_registry_contains_the_installed_014_artifact(self):
        runner = helper('verify-gradle-legacy-artifact-consumer.py')
        self.assertIn('0.1.4', [r['version'] for r in load_registry(runner.REGISTRY)['distributed']])

    def test_maven_current_registry_contains_the_installed_014_artifact(self):
        runner = helper('verify-maven-legacy-artifact-consumer.py')
        self.assertIn('0.1.4', [r['version'] for r in load_registry(runner.REGISTRY)['distributed']])

    def test_the_old_64_case_subset_cannot_complete_the_current_matrix(self):
        runner = helper('verify-current-entry-successor.py')
        full = runner.cases(load_registry(runner.REGISTRY))
        old = [c for c in full if c['legacy'] != '0.1.4']
        self.assertEqual(64, len(old))
        results = [{'case': c, 'outcome': 'PASS', 'observed': {'pid': index + 1}}
                   for index, c in enumerate(old)]
        status = runner.completion_status(old, results)
        self.assertEqual('INCOMPLETE', status['status'])
        self.assertFalse(status['fullA29Matrix'])


if __name__ == '__main__':
    unittest.main()
