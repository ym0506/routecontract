"""Offline contracts for real Maven legacy resolver evidence.

POM generation and synthetic byte buffers exercise the verifier only; these
checks do not launch Maven, resolve dependencies, or execute fake Java binaries.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT_ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    'maven_legacy_consumer_under_test', SCRIPT_ROOT / 'verify-maven-legacy-artifact-consumer.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
GROUP = 'io.github.ym0506.routecontract'
ADAPTER = 'routecontract-shardingsphere-5.5'
CORE = 'routecontract-core'
CURRENT = '0.2.0'
VERSIONS = ('0.1.0', '0.1.2', '0.1.3', '0.1.0-rc2')
N = '{http://maven.apache.org/POM/4.0.0}'


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


class MavenLegacyConsumerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.registry = MODULE.load_registry(SCRIPT_ROOT / 'legacy-artifact-inputs.json')
        self.plan = MODULE.cases(self.registry)
        self.by_id = {case['caseId']: case for case in self.plan}

    def test_case_grid_covers_all_public_versions_orders_and_policy_control(self):
        suffixes = {'alone', 'core-legacy-first', 'core-legacy-last', '552-legacy-first',
                    '552-legacy-last', 'bare-legacy-first', 'bare-legacy-last',
                    'managed-legacy-first', 'managed-legacy-last',
                    'strict-legacy-first', 'strict-legacy-last'}
        expected = {f'{version}-{suffix}' for version in VERSIONS for suffix in suffixes}
        expected.add('0.1.3-core-without-policy-control')
        self.assertEqual(expected, set(self.by_id))
        self.assertEqual(45, len(self.plan))
        self.assertEqual(len(self.plan), len(self.by_id), 'Duplicate cases cannot replace required coverage')
        self.assertEqual(Counter({'RESOLVED': 13, 'ENFORCER_REJECTED': 24, 'STRICT_RANGE_CONFLICT': 8}),
                         Counter(case['expected'] for case in self.plan))
        self.assertEqual(set(VERSIONS), {case['legacyVersion'] for case in self.plan})

    def test_generated_consumers_have_unique_direct_coordinates_and_explicit_policy(self):
        for case in self.plan:
            with self.subTest(case=case['caseId']):
                pom = MODULE.prepare_consumer(case, self.root / case['caseId'])
                root = ET.parse(pom).getroot()
                dependencies = root.findall(N + 'dependencies/' + N + 'dependency')
                keys = [(d.findtext(N + 'groupId'), d.findtext(N + 'artifactId'),
                         d.findtext(N + 'type', 'jar'), d.findtext(N + 'classifier', '')) for d in dependencies]
                self.assertEqual(len(keys), len(set(keys)), 'Maven must not receive duplicate same-GA declarations')
                self.assertEqual([(r['groupId'], r['artifactId'], r['version']) for r in case['requests']],
                                 [(d.findtext(N + 'groupId'), d.findtext(N + 'artifactId'),
                                   d.findtext(N + 'version')) for d in dependencies])
                plugins = root.findall(N + 'build/' + N + 'plugins/' + N + 'plugin')
                enforcers = [p for p in plugins if p.findtext(N + 'artifactId') == 'maven-enforcer-plugin']
                self.assertEqual(int(case['ownershipPolicy']), len(enforcers))
                if enforcers:
                    self.assertEqual('3.6.3', enforcers[0].findtext(N + 'version'))
                    rules = enforcers[0].find('.//' + N + 'bannedDependencies')
                    self.assertEqual('true', rules.findtext(N + 'searchTransitive'))
                    self.assertEqual([f'{GROUP}:{ADAPTER}:(,0.2.0)'],
                                     [e.text for e in rules.findall(N + 'excludes/' + N + 'exclude')])

    def test_strict_carriers_keep_singleton_ranges_and_consumers_have_no_management(self):
        repository = self.root / 'repository'
        inventory = MODULE.prepare_carriers(self.registry, repository, CURRENT)
        self.assertEqual(16, len(inventory))
        self.assertEqual(16, len({pin['relativePath'] for pin in inventory}))
        self.assertFalse(list(repository.rglob('*.jar')), 'Carriers are POM graph inputs, not fabricated JARs')
        by_module = {pin['module']: pin for pin in inventory}
        for case in self.plan:
            if case['kind'] not in ('strict', 'bare', 'managed'):
                continue
            with self.subTest(case=case['caseId']):
                requirements = []
                for request in case['requests']:
                    self.assertEqual('pom', request['type'])
                    pin = by_module[request['artifactId']]
                    payload = (repository / pin['relativePath']).read_bytes()
                    self.assertEqual(pin['sha256'], digest(payload))
                    carrier = ET.fromstring(payload)
                    self.assertEqual('pom', carrier.findtext(N + 'packaging'))
                    self.assertIsNone(carrier.find(N + 'dependencyManagement'))
                    dependencies = carrier.findall(N + 'dependencies/' + N + 'dependency')
                    self.assertEqual(1, len(dependencies))
                    self.assertEqual(GROUP, dependencies[0].findtext(N + 'groupId'))
                    self.assertEqual(ADAPTER, dependencies[0].findtext(N + 'artifactId'))
                    requirements.append(dependencies[0].findtext(N + 'version'))
                ordered = [case['legacyVersion'], CURRENT] if case['caseId'].endswith('first') else [CURRENT, case['legacyVersion']]
                self.assertEqual([f'[{v}]' for v in ordered] if case['kind'] == 'strict' else ordered, requirements)
                consumer = ET.parse(MODULE.prepare_consumer(case, self.root / case['caseId'])).getroot()
                management = consumer.find(N + 'dependencyManagement')
                if case['kind'] == 'managed':
                    managed = management.findall(N + 'dependencies/' + N + 'dependency')
                    self.assertEqual(1, len(managed))
                    self.assertEqual((GROUP, ADAPTER, CURRENT), tuple(managed[0].findtext(N + f) for f in ('groupId', 'artifactId', 'version')))
                else:
                    self.assertIsNone(management, 'Management must not rewrite strict requirements or bare controls')

    def test_bare_mediation_retains_maven_order_and_verbose_enforcer_outcomes(self):
        for version in VERSIONS:
            old_first = self.by_id[f'{version}-bare-legacy-first']
            new_first = self.by_id[f'{version}-bare-legacy-last']
            self.assertEqual([[ADAPTER, version]], old_first['expectedFirstParty'])
            self.assertEqual([[ADAPTER, CURRENT], [CORE, CURRENT]], new_first['expectedFirstParty'])
            for case in (old_first, new_first):
                self.assertEqual('ENFORCER_REJECTED', case['expected'])
                self.assertFalse(case['managedCurrentVersion'])
                self.assertTrue(case['ownershipPolicy'])
            for order in ('legacy-first', 'legacy-last'):
                managed = self.by_id[f'{version}-managed-{order}']
                self.assertTrue(managed['managedCurrentVersion'])
                self.assertEqual('RESOLVED', managed['expected'])
                self.assertEqual([[ADAPTER, CURRENT], [CORE, CURRENT]], managed['expectedFirstParty'])

    def test_mixed_components_and_disabled_policy_control_keep_the_actual_graph(self):
        for version in VERSIONS:
            for component, module in (('core', CORE), ('552', 'routecontract-shardingsphere-5.5.2')):
                forward = self.by_id[f'{version}-{component}-legacy-first']
                reverse = self.by_id[f'{version}-{component}-legacy-last']
                self.assertEqual([{'groupId': GROUP, 'artifactId': ADAPTER, 'version': version},
                                  {'groupId': GROUP, 'artifactId': module, 'version': CURRENT}], forward['requests'])
                self.assertEqual(list(reversed(forward['requests'])), reverse['requests'])
                self.assertEqual('ENFORCER_REJECTED', forward['expected'])
                self.assertEqual('ENFORCER_REJECTED', reverse['expected'])
        control = self.by_id['0.1.3-core-without-policy-control']
        protected = self.by_id['0.1.3-core-legacy-first']
        self.assertEqual(protected['requests'], control['requests'])
        self.assertEqual(protected['expectedFirstParty'], control['expectedFirstParty'])
        self.assertFalse(control['ownershipPolicy'])
        self.assertTrue(protected['ownershipPolicy'])
        self.assertEqual('RESOLVED', control['expected'])

    def graph(self, case):
        children = [{'groupId': GROUP, 'artifactId': module, 'version': version}
                    for module, version in case['expectedFirstParty']]
        if [ADAPTER, CURRENT] in case['expectedFirstParty']:
            children += [{'groupId': 'org.apache.shardingsphere', 'artifactId': 'shardingsphere-infra-executor', 'version': '5.5.3'}]
        return {'groupId': 'private.fixture', 'artifactId': 'consumer', 'version': '1', 'children': children}

    def test_selected_graph_rejects_legacy_bytes_missing_core_and_mixed_runtime(self):
        case = self.by_id['0.1.3-managed-legacy-first']
        graph = self.graph(case)
        self.assertEqual({(ADAPTER, CURRENT), (CORE, CURRENT)},
                         {(item['module'], item['version']) for item in MODULE.verify_selected_graph(graph, case)})
        mutations = []
        old = copy.deepcopy(graph); old['children'].append({'groupId': GROUP, 'artifactId': ADAPTER, 'version': '0.1.3'}); mutations.append(old)
        missing = copy.deepcopy(graph); missing['children'] = [c for c in missing['children'] if c['artifactId'] != CORE]; mutations.append(missing)
        no_executor = copy.deepcopy(graph); no_executor['children'].pop(); mutations.append(no_executor)
        mixed = copy.deepcopy(graph); mixed['children'].append({'groupId': 'org.apache.shardingsphere', 'artifactId': 'shardingsphere-infra-util', 'version': '5.5.2'}); mutations.append(mixed)
        for invalid in mutations:
            with self.subTest(graph=invalid), self.assertRaises(MODULE.VerificationError):
                MODULE.verify_selected_graph(invalid, case)
        bare_old = self.by_id['0.1.3-bare-legacy-first']
        MODULE.verify_selected_graph(self.graph(bare_old), bare_old)

    def cache_fixture(self):
        case = self.by_id['0.1.3-managed-legacy-first']
        cache = self.root / 'm2'
        inventory, paths = [], []
        for module, version in case['expectedFirstParty']:
            for extension in ('jar', 'pom'):
                name = f'{module}-{version}.{extension}'
                relative = f'{GROUP.replace(".", "/")}/{module}/{version}/{name}'
                payload = ('synthetic-verifier-buffer:' + name).encode()
                path = cache / relative
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
                marker = path.parent / '_remote.repositories'
                with marker.open('a') as stream:
                    stream.write(f'{name}>{MODULE.MIRROR_ID}=\n')
                inventory.append({'module': module, 'version': version, 'name': name, 'relativePath': relative,
                                  'sha256': digest(payload), 'byteCount': len(payload), 'origin': 'reviewed-staged-input'})
                if extension == 'jar':
                    paths.append(path)
        classpath = self.root / 'classpath.txt'
        classpath.write_text(os.pathsep.join(map(str, paths)))
        return case, cache, inventory, paths, classpath

    def test_exact_pinned_cache_and_classpath_are_accepted(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        MODULE.verify_cache(cache, self.root / 'repository', inventory)
        actual = MODULE.verify_classpath(classpath, case, cache, inventory)
        self.assertEqual({(ADAPTER, CURRENT), (CORE, CURRENT)}, {(p['module'], p['version']) for p in actual})
        self.assertEqual({digest(p.read_bytes()) for p in paths}, {p['sha256'] for p in actual})

    def test_changed_pinned_jar_is_rejected_in_cache_and_classpath(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        paths[0].write_bytes(paths[0].read_bytes() + b'changed')
        with self.assertRaisesRegex(MODULE.VerificationError, 'input pin'):
            MODULE.verify_cache(cache, self.root / 'repository', inventory)
        with self.assertRaisesRegex(MODULE.VerificationError, 'reviewed input bytes'):
            MODULE.verify_classpath(classpath, case, cache, inventory)

    def test_unknown_first_party_file_and_wrong_or_missing_origin_fail_closed(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        marker = paths[0].parent / '_remote.repositories'
        original = marker.read_text()
        for invalid in (original.replace(MODULE.MIRROR_ID, 'central'), original + f'{paths[0].name}>unexpected=\n'):
            marker.write_text(invalid)
            with self.subTest(marker=invalid), self.assertRaisesRegex(MODULE.VerificationError, 'origin'):
                MODULE.verify_cache(cache, self.root / 'repository', inventory)
        marker.unlink()
        with self.assertRaisesRegex(MODULE.VerificationError, 'origin'):
            MODULE.verify_cache(cache, self.root / 'repository', inventory)
        marker.write_text(original)
        unknown = paths[0].with_name('unreviewed.jar'); unknown.write_bytes(b'unreviewed')
        with self.assertRaisesRegex(MODULE.VerificationError, 'input pin'):
            MODULE.verify_cache(cache, self.root / 'repository', inventory)

    def test_classpath_rejects_missing_duplicate_legacy_and_external_files(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        legacy = cache / GROUP.replace('.', '/') / ADAPTER / '0.1.3' / f'{ADAPTER}-0.1.3.jar'
        legacy.parent.mkdir(parents=True); legacy.write_bytes(b'legacy-unreviewed')
        alternatives = [paths[:1], paths + [paths[0]], paths + [legacy], paths + [self.root / 'outside.jar']]
        for invalid in alternatives:
            classpath.write_text(os.pathsep.join(map(str, invalid)))
            with self.subTest(paths=invalid), self.assertRaises(MODULE.VerificationError):
                MODULE.verify_classpath(classpath, case, cache, inventory)

    def test_final_jar_symlink_is_rejected_even_with_matching_bytes(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        outside = self.root / 'copy.jar'; outside.write_bytes(paths[0].read_bytes())
        paths[0].unlink(); paths[0].symlink_to(outside)
        with self.assertRaises(MODULE.VerificationError):
            MODULE.verify_cache(cache, self.root / 'repository', inventory)
        with self.assertRaises(MODULE.VerificationError):
            MODULE.verify_classpath(classpath, case, cache, inventory)

    def test_classpath_rejects_parent_traversal_with_valid_first_party_entries(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        outside = self.root / 'outside' / 'extra.jar'
        outside.parent.mkdir(); outside.write_bytes(b'external-verifier-buffer')
        traversing = cache / '..' / 'outside' / 'extra.jar'
        classpath.write_text(os.pathsep.join(map(str, paths + [traversing])))
        with self.assertRaises(MODULE.VerificationError):
            MODULE.verify_classpath(classpath, case, cache, inventory)

    def test_symlinked_artifact_directory_cannot_bypass_cache_origin_checks(self):
        case, cache, inventory, paths, classpath = self.cache_fixture()
        artifact_directory = paths[0].parents[1]
        outside = self.root / 'external' / artifact_directory.name
        outside.parent.mkdir(); artifact_directory.rename(outside)
        for marker in outside.rglob('_remote.repositories'):
            marker.unlink()
        artifact_directory.symlink_to(outside, target_is_directory=True)
        with self.subTest(check='cache'), self.assertRaises(MODULE.VerificationError):
            MODULE.verify_cache(cache, self.root / 'repository', inventory)
        with self.subTest(check='classpath'), self.assertRaises(MODULE.VerificationError):
            MODULE.verify_classpath(classpath, case, cache, inventory)

    def enforcer_failure(self):
        return ('[ERROR] Rule 0: org.apache.maven.enforcer.rules.dependency.BannedDependencies failed with message:\n'
                f'{GROUP}:{ADAPTER}:jar:0.1.3 <--- banned via the exclude/include list\n')

    def strict_failure(self):
        return (f'Could not resolve version conflict among [{GROUP}:{ADAPTER}:jar:[0.1.3], '
                f'{GROUP}:{ADAPTER}:jar:[0.2.0]]')

    def test_failure_classifier_accepts_only_the_expected_semantic_cause(self):
        banned = self.by_id['0.1.3-core-legacy-first']
        strict = self.by_id['0.1.3-strict-legacy-first']
        MODULE.verify_failure(self.enforcer_failure(), banned)
        MODULE.verify_failure(self.strict_failure(), strict)
        for output, case in [(self.enforcer_failure(), strict), (self.strict_failure(), banned),
                             ('DependencyConvergence failed\n[0.1.3] [0.2.0]', strict),
                             ('Could not resolve version conflict among [0.1.3] [0.2.1]', strict),
                             (self.enforcer_failure().replace(':jar:0.1.3', ':jar:0.1.2'), banned),
                             (self.strict_failure() + '\n' + self.enforcer_failure(), strict)]:
            with self.subTest(output=output, expected=case['expected']), self.assertRaises(MODULE.VerificationError):
                MODULE.verify_failure(output, case)

    def test_strict_classifier_accepts_both_maven_singleton_renderings(self):
        for version in VERSIONS:
            case = self.by_id[f'{version}-strict-legacy-first']
            for normalized in (False, True):
                def requirement(value):
                    return f'[{value},{value}]' if normalized else f'[{value}]'
                output = ('[ERROR] Could not resolve version conflict among ['
                          f'fixture:old:pom:1 -> {GROUP}:{ADAPTER}:jar:{requirement(version)}, '
                          f'fixture:new:pom:1 -> {GROUP}:{ADAPTER}:jar:{requirement(CURRENT)}]')
                with self.subTest(version=version, normalized=normalized):
                    MODULE.verify_failure(output, case)

    def test_enforcer_classifier_binds_exact_legacy_version_to_banned_node(self):
        case = self.by_id['0.1.3-core-legacy-first']
        for output in [self.enforcer_failure().replace(':jar:0.1.3 ', ':jar:0.1.30 '),
                       self.enforcer_failure().replace(':jar:0.1.3 ', ':jar:0.1.3-SNAPSHOT '),
                       self.enforcer_failure().replace(f'{GROUP}:{ADAPTER}:jar:0.1.3', 'other:library:jar:1')
                       + f'\nExpected elsewhere: {GROUP}:{ADAPTER}:jar:0.1.3']:
            with self.subTest(output=output), self.assertRaises(MODULE.VerificationError):
                MODULE.verify_failure(output, case)
        MODULE.verify_failure(self.enforcer_failure().replace(':jar:0.1.3 ', ':jar:0.1.3:compile '), case)

    def test_strict_classifier_binds_both_singletons_to_routecontract_conflict_record(self):
        case = self.by_id['0.1.3-strict-legacy-first']
        failures = [
            self.strict_failure().replace(GROUP, 'unrelated.group'),
            self.strict_failure().replace(f'{GROUP}:{ADAPTER}:jar:[0.2.0]', 'other:library:jar:[0.2.0]'),
            self.strict_failure().replace(':jar:[0.2.0]', ':jar:[0.2.0,0.2.1]'),
            self.strict_failure().replace(':jar:[0.2.0]', ':jar:[0.2.0,0.2.0-SNAPSHOT]'),
            'Could not resolve version conflict among unrelated:library:jar:[1]\n'
            f'Elsewhere {GROUP}:{ADAPTER}:jar:[0.1.3] {GROUP}:{ADAPTER}:jar:[0.2.0]',
        ]
        for output in failures:
            with self.subTest(output=output), self.assertRaises(MODULE.VerificationError):
                MODULE.verify_failure(output, case)

    def test_infrastructure_failure_cannot_be_counted_even_alongside_expected_text(self):
        failures = ['Could not transfer artifact', 'Could not find artifact', 'Checksum validation failed',
                    'PluginResolutionException', 'Non-resolvable parent POM', 'Could not transfer metadata']
        for case, expected in [(self.by_id['0.1.3-core-legacy-first'], self.enforcer_failure()),
                               (self.by_id['0.1.3-strict-legacy-first'], self.strict_failure())]:
            for failure in failures:
                for output in (failure, expected + '\n' + failure):
                    with self.subTest(expected=case['expected'], failure=output), self.assertRaisesRegex(MODULE.VerificationError, 'infrastructure'):
                        MODULE.verify_failure(output, case)


if __name__ == '__main__':
    unittest.main()
