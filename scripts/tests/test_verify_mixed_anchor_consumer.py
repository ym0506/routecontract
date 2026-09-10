import copy
import importlib.util
import itertools
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('a09', ROOT / 'scripts/verify-mixed-anchor-consumer.py')
a09 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a09
spec.loader.exec_module(a09)


class MixedAnchorTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in a09.cases() if case['category'] == 'mixed' and case['spi'] == '5.5.3')
        self.core = {'path': '/core.jar', 'sha256': 'a' * 64}
        self.anchors = {role: {'className': name, 'origin': '/' + role + '.jar',
            'sha256': role[0] * 64, 'implementationVersion': self.case[role],
            'classResourcePresent': True, 'module': role}
            for role, name in a09.anchor_classes(self.case['adapter']).items()}
        lane = self.case['adapter'].replace('.', '')
        self.observed = {'pid': 100, 'javaVersion': '17.0.15', 'adapter': self.case['adapter'],
            'returned': False, 'actionEntries': 0, 'snapshot': None,
            'exceptionClasses': ['java.lang.IllegalStateException'],
            'exceptionMessages': [a09.MARKER + ': executor=5.5.2, spi=5.5.3, database=5.5.2'],
            'stackFrames': ['io.github.ym0506.routecontract.shardingsphere' + lane + '.internal.ShardingSphere' + lane + 'HookConstructionGuard.verifyAnchorVersions'],
            'linkageFailure': False, 'newEntry': {'className': 'io.github.ym0506.routecontract.api.RouteContract',
                'loaded': True, 'origin': '/core.jar', 'sha256': 'a' * 64, 'implementationVersion': '0.2.0'},
            'anchors': {role: {key: value for key, value in expected.items() if key not in ('classResourcePresent', 'module')} | {'loaded': True}
                for role, expected in self.anchors.items()}}

    def classify(self):
        return a09.classify(self.case, self.observed, self.anchors, self.core)

    def test_all_nominal_mixed_tuples_and_orders_retained(self):
        mixed = [case for case in a09.cases() if case['category'] == 'mixed']
        wanted = {(e, s, d, order) for e, s, d in itertools.product(a09.VERSIONS, repeat=3)
            if len({e, s, d}) > 1 for order in ('forward', 'reverse')}
        self.assertEqual(12, len(mixed))
        self.assertEqual(wanted, {(case['executor'], case['spi'], case['database'], case['order']) for case in mixed})
        self.assertTrue(all(case['adapter'] == case['database'] and case['expected'] == a09.MARKER for case in mixed))

    def test_missing_spi_tuples_are_not_skipped(self):
        mixed = [case for case in a09.cases() if case['category'] == 'mixed' and case['spi'] == '5.5.2']
        self.assertEqual(6, len(mixed))

    def test_exact_guard_rejection_passes(self):
        self.assertEqual('PASS', self.classify())

    def test_generated_marker_without_guard_does_not_pass(self):
        self.observed['stackFrames'] = ['io.github.ym0506.routecontract.consumer.MixedAnchorProbe.main']
        self.assertEqual('GUARD_NOT_OBSERVED', self.classify())

    def test_wrong_stable_marker_is_failure(self):
        self.observed['exceptionMessages'] = ['RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: anchor unavailable']
        self.assertEqual('WRONG_DIAGNOSTIC', self.classify())

    def test_mentioning_expected_marker_inside_wrong_diagnostic_fails(self):
        self.observed['exceptionMessages'] = ['RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: expected ' + a09.MARKER + ': but unavailable']
        self.assertEqual('WRONG_DIAGNOSTIC', self.classify())

    def test_correct_nested_marker_does_not_hide_wrong_public_top_level_code(self):
        self.observed['exceptionClasses'] = ['java.lang.IllegalStateException', 'java.lang.IllegalStateException']
        self.observed['exceptionMessages'] = ['RC_ADAPTER_CLASSLOADER_MISMATCH: service failed', a09.MARKER + ': mixed']
        self.assertEqual('WRONG_DIAGNOSTIC', self.classify())

    def test_action_or_empty_success_is_failure(self):
        self.observed['actionEntries'] = 1
        self.assertEqual('ACTION_OR_RESULT_ESCAPED', self.classify())
        self.observed['actionEntries'] = 0
        self.observed['returned'] = True
        self.assertEqual('ACTION_OR_RESULT_ESCAPED', self.classify())

    def test_linkage_cause_never_passes(self):
        self.observed['linkageFailure'] = True
        self.assertEqual('LINKAGE_FAILURE', self.classify())

    def test_wrong_actual_anchor_hash_is_failure(self):
        self.observed['anchors']['executor']['sha256'] = '0' * 64
        self.assertEqual('WRONG_ANCHOR_ORIGIN', self.classify())

    def test_expected_rejection_can_pass_when_official_anchor_cannot_load(self):
        expected = self.anchors['spi']
        expected['classResourcePresent'] = False
        self.observed['anchors']['spi'] = {'className': expected['className'], 'loaded': False,
            'loadFailureClass': 'java.lang.ClassNotFoundException', 'loadFailureMessage': expected['className']}
        self.assertEqual('PASS', self.classify())
        self.observed['exceptionMessages'] = ['RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: missing SPI']
        self.assertEqual('WRONG_DIAGNOSTIC', self.classify())

    def test_malformed_missing_anchor_exception_class_does_not_pass(self):
        name = self.anchors['spi']['className']
        self.observed['anchors']['spi'] = {'className': name, 'loaded': False,
            'loadFailureClass': 1, 'loadFailureMessage': name}
        self.assertEqual('INVALID_ANCHOR_OBSERVATION', self.classify())

    def test_partial_duplicate_or_repeated_pid_never_complete(self):
        rows = [{'case': case, 'outcome': 'PASS', 'observed': {'pid': index + 1}}
                for index, case in enumerate(a09.cases())]
        self.assertEqual('VERIFIED', a09.completion_status(rows)['status'])
        self.assertFalse(a09.completion_status(rows)['fullA09Acceptance'])
        self.assertEqual('INCOMPLETE', a09.completion_status(rows, partial=True)['status'])
        self.assertEqual('INCOMPLETE', a09.completion_status(rows[:-1])['status'])
        rows[-1]['observed']['pid'] = 1
        self.assertEqual('INCOMPLETE', a09.completion_status(rows)['status'])
        rows[-1] = copy.deepcopy(rows[0])
        self.assertEqual('INCOMPLETE', a09.completion_status(rows)['status'])

    def test_one_failure_keeps_original_matrix_failed(self):
        rows = [{'case': case, 'outcome': 'PASS', 'observed': {'pid': index + 1}}
                for index, case in enumerate(a09.cases())]
        rows[4]['outcome'] = 'WRONG_DIAGNOSTIC'
        self.assertEqual('FAILED', a09.completion_status(rows)['status'])

    def test_physical_order_reverses_exact_anchors_without_duplicates(self):
        graphs = {}
        for version in a09.VERSIONS:
            graphs[version] = {'classes': ['/classes-' + version], 'artifacts': [
                {'group': a09.SS, 'module': module, 'path': '/' + module + '-' + version + '.jar'}
                for module in ('shardingsphere-infra-executor', 'shardingsphere-infra-spi', a09.DATABASE_MODULES[version])]
                + [{'group': a09.GROUP, 'module': 'routecontract-core', 'path': '/core.jar'}]}
        forward = a09.assemble_classpath(self.case | {'order': 'forward'}, graphs)
        reverse = a09.assemble_classpath(self.case | {'order': 'reverse'}, graphs)
        self.assertEqual(forward[1:4], list(reversed(reverse[1:4])))
        self.assertEqual(set(forward), set(reverse))
        self.assertEqual(5, len(forward))
        self.assertEqual(len(forward), len(set(forward)))

    def test_clean_identity_requires_all_fields_and_boolean_supported(self):
        case = next(case for case in a09.cases() if case['category'] == 'clean')
        observed = copy.deepcopy(self.observed)
        anchors = copy.deepcopy(self.anchors)
        observed.update(adapter=case['adapter'], returned=True, actionEntries=1, exceptionClasses=[],
                        exceptionMessages=[], stackFrames=[], linkageFailure=False)
        for role, name in a09.anchor_classes(case['adapter']).items():
            anchors[role].update(className=name, implementationVersion=case[role])
            observed['anchors'][role].update(className=name, implementationVersion=case[role])
        identity = {'adapterId': 'apache-shardingsphere-jdbc/sql-execution-hook', 'adapterContractVersion': 1,
            'infraExecutorImplementationVersion': case['adapter'], 'infraSpiImplementationVersion': case['adapter'],
            'supported': True}
        observed['snapshot'] = {'schemaVersion': 2, 'status': 'INCOMPLETE', 'observedPhysicalAttemptCount': 0,
            'collectorDiagnostics': ['RC_NO_START_CALLBACK_OBSERVED'], 'runtimeIdentity': identity}
        self.assertEqual('PASS', a09.classify(case, observed, anchors, self.core))
        for invalid in [False, 1, None, 'true']:
            identity['supported'] = invalid
            self.assertEqual('CONTROL_FAILED', a09.classify(case, observed, anchors, self.core))
        del identity['supported']
        self.assertEqual('CONTROL_FAILED', a09.classify(case, observed, anchors, self.core))
        identity['supported'] = True
        identity['extra'] = True
        self.assertEqual('CONTROL_FAILED', a09.classify(case, observed, anchors, self.core))

    def test_probe_has_no_required_rejection_literal(self):
        source = (a09.FIXTURE / 'src/test/java/io/github/ym0506/routecontract/consumer/MixedAnchorProbe.java').read_text()
        self.assertNotIn(a09.MARKER, source)
        self.assertLess(source.index('RouteContract.capture('), source.index('anchors.put("executor"'))


if __name__ == '__main__':
    unittest.main()
