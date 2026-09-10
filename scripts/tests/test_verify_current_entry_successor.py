from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'current_entry_successor_test', ROOT / 'scripts/verify-current-entry-successor.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)

RUNTIMES = ('5.5.2', '5.5.3')
LEGACIES = ('0.1.0', '0.1.0-rc2', '0.1.2', '0.1.3')
ORDERS = ('legacy-first', 'legacy-last')
CURRENT_METHODS = ('current-capture', 'current-capture-result')
COMPATIBILITY_METHODS = ('compatibility-capture', 'compatibility-capture-result')


class CurrentEntrySuccessorPlanTest(unittest.TestCase):
    def setUp(self):
        registry = json.loads((ROOT / 'scripts/legacy-artifact-inputs.json').read_text())
        self.plan = helper.cases(registry)

    def test_plan_has_64_distinct_cells_and_all_required_categories(self):
        self.assertEqual(64, len(self.plan))
        self.assertEqual(64, len({case['id'] for case in self.plan}))
        self.assertEqual(Counter({
            'COLLISION': 48,
            'CLEAN_NO_SQL': 8,
            'CLEAN_SQL': 2,
            'CLEAN_CAPTURED_SQL': 2,
            'RC_ADAPTER_NOT_FOUND': 2,
            'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME': 2,
        }), Counter(case['expected'] for case in self.plan))
        for case in self.plan:
            self.assertTrue({'id', 'runtime', 'mode', 'legacy', 'order', 'adapter',
                             'expected', 'category'}.issubset(case))

    def test_each_distributed_legacy_runs_both_current_methods_in_both_orders_and_runtimes(self):
        cells = [case for case in self.plan
                 if case['expected'] == 'COLLISION' and case['mode'] != 'sql']
        expected = {(legacy, runtime, order, mode)
                    for legacy in LEGACIES for runtime in RUNTIMES
                    for order in ORDERS for mode in CURRENT_METHODS}
        self.assertEqual(32, len(cells))
        self.assertEqual(expected, {(case['legacy'], case['runtime'], case['order'], case['mode'])
                                    for case in cells})

    def test_ordinary_sql_collisions_are_independent_of_any_capture_entry(self):
        cells = [case for case in self.plan
                 if case['expected'] == 'COLLISION' and case['mode'] == 'sql']
        self.assertEqual(16, len(cells))
        self.assertEqual({(legacy, runtime, order)
                          for legacy in LEGACIES for runtime in RUNTIMES for order in ORDERS},
                         {(case['legacy'], case['runtime'], case['order']) for case in cells})

    def test_clean_controls_include_compatibility_current_ordinary_sql_and_full_startup_sql(self):
        cells = [case for case in self.plan if case['expected'].startswith('CLEAN_')]
        self.assertEqual(12, len(cells))
        self.assertEqual({(runtime, mode) for runtime in RUNTIMES
                          for mode in (*CURRENT_METHODS, *COMPATIBILITY_METHODS, 'sql', 'startup-sql')},
                         {(case['runtime'], case['mode']) for case in cells})
        self.assertTrue(all(case['legacy'] is None and case['order'] is None for case in cells))

    def test_startup_rejections_cover_missing_and_wrong_adapter_on_each_runtime(self):
        cells = [case for case in self.plan if case['mode'] == 'startup']
        self.assertEqual(4, len(cells))
        self.assertEqual({(runtime, expected) for runtime in RUNTIMES
                          for expected in ('RC_ADAPTER_NOT_FOUND', 'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME')},
                         {(case['runtime'], case['expected']) for case in cells})
        self.assertTrue(all(case['legacy'] is None for case in cells))


class CurrentEntrySuccessorClassificationTest(unittest.TestCase):
    def setUp(self):
        registry = json.loads((ROOT / 'scripts/legacy-artifact-inputs.json').read_text())
        self.plan = helper.cases(registry)

    def case(self, expected, mode=None, runtime='5.5.2'):
        return next(case for case in self.plan if case['expected'] == expected
                    and case['runtime'] == runtime and (mode is None or case['mode'] == mode))

    @staticmethod
    def identity(runtime):
        return {'adapterId': 'apache-shardingsphere-jdbc/sql-execution-hook',
                'adapterContractVersion': 1, 'infraExecutorImplementationVersion': runtime,
                'infraSpiImplementationVersion': runtime}

    @staticmethod
    def origins(case):
        shadowed = '/legacy.jar' if case['legacy'] and case['order'] == 'legacy-first' else '/core.jar'
        return {'newEntryOrigin': '/core.jar', 'guardOrigin': '/core.jar',
                'compatibilityEntryOrigin': shadowed, 'captureRegistryOrigin': shadowed}

    def observation(self, case):
        expected = case['expected']
        mode = case['mode']
        clean = expected.startswith('CLEAN_')
        captured = expected in ('CLEAN_NO_SQL', 'CLEAN_CAPTURED_SQL')
        sql = expected in ('CLEAN_SQL', 'CLEAN_CAPTURED_SQL')
        observed = {
            'mode': mode, 'pid': 17, 'javaVersion': '17.0.15',
            'shardingSphereVersion': case['runtime'], **self.origins(case),
            'returned': clean, 'actionEntered': captured, 'actionEntries': 1 if captured else 0,
            'physicalBusinessExecutions': 1 if sql else 0,
            'businessRows': ['201:3:PAID'] if sql else [],
            'datasourceConstructionEntered': mode in ('sql', 'startup-sql'),
            'captureSnapshot': None, 'resultValue': None, 'verifiedRuntimeIdentity': None,
            'exceptionClasses': [], 'exceptionMessages': [], 'stackFrames': [],
            'linkageFailure': False,
            'boundary': 'The driver counter covers the fixed synchronous business PreparedStatement only.',
        }
        if captured:
            observed['captureSnapshot'] = {
                'schemaVersion': 2, 'status': 'COMPLETE' if sql else 'INCOMPLETE',
                'observedPhysicalAttemptCount': 1 if sql else 0,
                'collectorDiagnostics': [] if sql else ['RC_NO_START_CALLBACK_OBSERVED'],
                'runtimeIdentity': self.identity(case['runtime']),
            }
            if mode.endswith('-result'):
                observed['resultValue'] = 'current-entry-sentinel'
            elif mode == 'startup-sql':
                observed['resultValue'] = ['201:3:PAID']
                observed['verifiedRuntimeIdentity'] = self.identity(case['runtime'])
        if not clean:
            marker = 'RC_LEGACY_ADAPTER_COLLISION' if expected == 'COLLISION' else expected
            observed['exceptionClasses'] = ['java.lang.IllegalStateException']
            observed['exceptionMessages'] = [marker + ': actual runtime rejection']
            if mode in CURRENT_METHODS:
                observed['stackFrames'] = [
                    'io.github.ym0506.routecontract.internal.CurrentRuntimeGuard.verifyLegacyResources']
            elif mode == 'sql':
                version = case['runtime'].replace('.', '')
                observed['stackFrames'] = [
                    f'io.github.ym0506.routecontract.shardingsphere{version}.internal.'
                    f'ShardingSphere{version}HookConstructionGuard.verify']
            else:
                observed['stackFrames'] = ['io.github.ym0506.routecontract.internal.RuntimeAdapterRegistry.verify']
        return observed

    def assertRejected(self, case, observed):
        self.assertNotEqual('PASS', helper.classify(case, observed, self.origins(case)))

    def test_all_planned_modes_accept_complete_matching_observations(self):
        for case in self.plan:
            with self.subTest(case=case['id']):
                self.assertEqual('PASS', helper.classify(case, self.observation(case), self.origins(case)))

    def test_marker_cannot_hide_action_sql_rows_linkage_or_silent_return(self):
        for mode in (*CURRENT_METHODS, 'sql'):
            case = self.case('COLLISION', mode)
            for change in ({'actionEntered': True}, {'actionEntries': 1},
                           {'physicalBusinessExecutions': 1}, {'businessRows': ['201:3:PAID']},
                           {'linkageFailure': True}, {'returned': True},
                           {'exceptionClasses': ['java.lang.AbstractMethodError']},
                           {'exceptionMessages': ['RouteContract supports exactly ShardingSphere 5.5.3']}):
                with self.subTest(mode=mode, change=change):
                    self.assertRejected(case, dict(self.observation(case), **change))

    def test_current_capture_collision_requires_the_current_guard_in_the_cause_stack(self):
        for mode in CURRENT_METHODS:
            case = self.case('COLLISION', mode)
            self.assertRejected(case, dict(self.observation(case), stackFrames=['fixture.FakeGuard.verify']))

    def test_sql_collision_requires_datasource_entry_and_the_exact_constructor_guard(self):
        for runtime in RUNTIMES:
            case = self.case('COLLISION', 'sql', runtime)
            other = '553' if runtime == '5.5.2' else '552'
            for change in ({'datasourceConstructionEntered': False},
                           {'stackFrames': ['fixture.FakeGuard.verify']},
                           {'stackFrames': ['io.github.ym0506.routecontract.internal.CurrentRuntimeGuard.verify']},
                           {'stackFrames': [f'io.github.ym0506.routecontract.shardingsphere{other}.internal.'
                                            f'ShardingSphere{other}HookConstructionGuard.verify']}):
                with self.subTest(runtime=runtime, change=change):
                    self.assertRejected(case, dict(self.observation(case), **change))

    def test_class_origin_and_exact_execution_environment_are_independent_proofs(self):
        for expected in ('COLLISION', 'CLEAN_NO_SQL', 'CLEAN_SQL', 'CLEAN_CAPTURED_SQL',
                         'RC_ADAPTER_NOT_FOUND', 'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME'):
            case = self.case(expected)
            for field in self.origins(case):
                with self.subTest(expected=expected, origin=field):
                    self.assertRejected(case, dict(self.observation(case), **{field: '/unreviewed.jar'}))
            for change in ({'javaVersion': '21.0.11'}, {'shardingSphereVersion': '5.5.3'},
                           {'mode': 'unrelated-mode'}, {'pid': 0}):
                with self.subTest(expected=expected, change=change):
                    self.assertRejected(case, dict(self.observation(case), **change))

    def test_missing_proof_fields_and_counter_type_confusion_cannot_pass(self):
        for expected in ('COLLISION', 'CLEAN_NO_SQL', 'CLEAN_CAPTURED_SQL', 'RC_ADAPTER_NOT_FOUND'):
            case = self.case(expected)
            observed = self.observation(case)
            for field in set(observed) - {'boundary'}:
                incomplete = copy.deepcopy(observed)
                del incomplete[field]
                with self.subTest(expected=expected, missing=field):
                    self.assertRejected(case, incomplete)
            for field in ('actionEntries', 'physicalBusinessExecutions', 'pid'):
                with self.subTest(expected=expected, counter=field):
                    self.assertRejected(case, dict(observed, **{field: bool(observed[field])}))

    def test_no_sql_controls_require_exact_action_count_empty_driver_and_incomplete_snapshot(self):
        for mode in (*CURRENT_METHODS, *COMPATIBILITY_METHODS):
            case = self.case('CLEAN_NO_SQL', mode)
            for change in ({'actionEntries': 0}, {'actionEntries': 2}, {'actionEntered': False},
                           {'physicalBusinessExecutions': 1}, {'businessRows': ['201:3:PAID']},
                           {'datasourceConstructionEntered': True}, {'captureSnapshot': None},
                           {'verifiedRuntimeIdentity': self.identity(case['runtime'])}):
                with self.subTest(mode=mode, change=change):
                    self.assertRejected(case, dict(self.observation(case), **change))
            for change in ({'schemaVersion': 1}, {'status': 'COMPLETE'},
                           {'observedPhysicalAttemptCount': 1}, {'collectorDiagnostics': []}):
                observed = self.observation(case)
                observed['captureSnapshot'].update(change)
                with self.subTest(mode=mode, snapshot=change):
                    self.assertRejected(case, observed)
            if mode.endswith('-result'):
                self.assertRejected(case, dict(self.observation(case), resultValue=None))
                self.assertRejected(case, dict(self.observation(case), resultValue='wrong-result'))

    def test_sql_controls_require_exact_rows_one_driver_execution_and_correct_capture_boundary(self):
        for expected, mode in (('CLEAN_SQL', 'sql'), ('CLEAN_CAPTURED_SQL', 'startup-sql')):
            case = self.case(expected, mode)
            for change in ({'physicalBusinessExecutions': 0}, {'physicalBusinessExecutions': 2},
                           {'businessRows': []}, {'businessRows': ['202:3:PAID']},
                           {'datasourceConstructionEntered': False}):
                with self.subTest(mode=mode, change=change):
                    self.assertRejected(case, dict(self.observation(case), **change))
        case = self.case('CLEAN_SQL', 'sql')
        for change in ({'actionEntries': 1, 'actionEntered': True},
                       {'verifiedRuntimeIdentity': self.identity(case['runtime'])},
                       {'captureSnapshot': self.observation(self.case('CLEAN_NO_SQL'))['captureSnapshot']}):
            self.assertRejected(case, dict(self.observation(case), **change))
        case = self.case('CLEAN_CAPTURED_SQL', 'startup-sql')
        for change in ({'actionEntries': 0, 'actionEntered': False}, {'actionEntries': 2},
                       {'resultValue': None}, {'resultValue': ['202:3:PAID']},
                       {'verifiedRuntimeIdentity': None}, {'captureSnapshot': None}):
            self.assertRejected(case, dict(self.observation(case), **change))
        for change in ({'schemaVersion': 1}, {'status': 'INCOMPLETE'},
                       {'observedPhysicalAttemptCount': 0}, {'collectorDiagnostics': ['RC_NO_START_CALLBACK_OBSERVED']}):
            observed = self.observation(case)
            observed['captureSnapshot'].update(change)
            self.assertRejected(case, observed)

    def test_snapshot_and_startup_identity_require_every_exact_semantic_component(self):
        wrong = {'adapterId': 'fixture/unrelated', 'adapterContractVersion': 2,
                 'infraExecutorImplementationVersion': '5.5.3', 'infraSpiImplementationVersion': '5.5.3'}
        for expected in ('CLEAN_NO_SQL', 'CLEAN_CAPTURED_SQL'):
            case = self.case(expected)
            fields = ['captureSnapshot'] + (['verifiedRuntimeIdentity'] if expected == 'CLEAN_CAPTURED_SQL' else [])
            for holder in fields:
                for name, value in wrong.items():
                    for missing in (False, True):
                        observed = self.observation(case)
                        identity = (observed[holder]['runtimeIdentity'] if holder == 'captureSnapshot'
                                    else observed[holder])
                        if missing:
                            del identity[name]
                        else:
                            identity[name] = value
                        with self.subTest(expected=expected, holder=holder, field=name, missing=missing):
                            self.assertRejected(case, observed)

    def test_snapshot_integer_fields_cannot_be_forged_with_equal_booleans_or_floats(self):
        for expected in ('CLEAN_NO_SQL', 'CLEAN_CAPTURED_SQL'):
            case = self.case(expected)
            for field, value in (('schemaVersion', 2.0),
                                 ('observedPhysicalAttemptCount', expected == 'CLEAN_CAPTURED_SQL')):
                observed = self.observation(case)
                observed['captureSnapshot'][field] = value
                with self.subTest(expected=expected, field=field):
                    self.assertRejected(case, observed)
            observed = self.observation(case)
            observed['captureSnapshot']['runtimeIdentity']['adapterContractVersion'] = True
            self.assertRejected(case, observed)
        case = self.case('CLEAN_CAPTURED_SQL')
        observed = self.observation(case)
        observed['verifiedRuntimeIdentity']['adapterContractVersion'] = True
        self.assertRejected(case, observed)

    def test_startup_rejections_require_actual_pre_datasource_pre_action_failure(self):
        for expected in ('RC_ADAPTER_NOT_FOUND', 'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME'):
            case = self.case(expected, 'startup')
            for change in ({'datasourceConstructionEntered': True}, {'actionEntered': True},
                           {'actionEntries': 1}, {'physicalBusinessExecutions': 1},
                           {'businessRows': ['201:3:PAID']}, {'returned': True},
                           {'verifiedRuntimeIdentity': self.identity(case['runtime'])},
                           {'exceptionMessages': ['RC_LEGACY_ADAPTER_COLLISION: unrelated rejection']}):
                with self.subTest(expected=expected, change=change):
                    self.assertRejected(case, dict(self.observation(case), **change))


class CurrentEntrySuccessorCompletionTest(unittest.TestCase):
    def setUp(self):
        registry = json.loads((ROOT / 'scripts/legacy-artifact-inputs.json').read_text())
        self.plan = helper.cases(registry)
        self.results = [{'case': copy.deepcopy(case), 'outcome': 'PASS', 'observed': {'pid': 1000 + index}}
                        for index, case in enumerate(self.plan)]

    def test_only_complete_canonical_plan_with_fresh_jvms_is_verified(self):
        status = helper.completion_status(self.plan, self.results)
        self.assertEqual('VERIFIED', status['status'])
        self.assertTrue(status['fullA29Matrix'])
        self.assertEqual(64, status['executedCount'])
        self.assertEqual(64, status['passedCount'])

    def test_successful_partial_selection_never_becomes_full_matrix(self):
        for required, results, partial in ((self.plan, self.results[:8], False),
                                           (self.plan[:8], self.results[:8], False),
                                           (self.plan, self.results, True),
                                           (self.plan, [], False)):
            with self.subTest(required=len(required), executed=len(results), partial=partial):
                status = helper.completion_status(required, results, partial=partial)
                self.assertEqual('INCOMPLETE', status['status'])
                self.assertFalse(status['fullA29Matrix'])

    def test_failed_observation_stays_failed_even_when_selection_is_partial(self):
        self.results[0]['outcome'] = 'WRONG_DIAGNOSTIC'
        for partial in (False, True):
            status = helper.completion_status(self.plan, self.results, partial=partial)
            self.assertEqual('FAILED', status['status'])
            self.assertEqual(63, status['passedCount'])

    def test_duplicate_missing_or_rewritten_case_cannot_supply_canonical_coverage(self):
        mutated_case = copy.deepcopy(self.results)
        mutated_case[0]['case']['mode'] = 'startup'
        duplicate = self.results[:-1] + [copy.deepcopy(self.results[0])]
        extra = self.results + [copy.deepcopy(self.results[0])]
        for results in (mutated_case, duplicate, extra):
            self.assertNotEqual('VERIFIED', helper.completion_status(self.plan, results)['status'])
        duplicate_required = self.plan[:-1] + [self.plan[0]]
        self.assertNotEqual('VERIFIED', helper.completion_status(duplicate_required, duplicate)['status'])

    def test_reused_missing_or_invalid_process_identity_cannot_prove_fresh_jvms(self):
        for pid in (self.results[1]['observed']['pid'], 0, -1, True, '1000', None):
            results = copy.deepcopy(self.results)
            results[0]['observed']['pid'] = pid
            with self.subTest(pid=pid):
                self.assertNotEqual('VERIFIED', helper.completion_status(self.plan, results)['status'])
        results = copy.deepcopy(self.results)
        del results[0]['observed']['pid']
        self.assertNotEqual('VERIFIED', helper.completion_status(self.plan, results)['status'])


class CurrentEntrySuccessorInputBindingTest(unittest.TestCase):
    @staticmethod
    def sha(content):
        return hashlib.sha256(content).hexdigest()

    def fixture_graph(self, root):
        jar = root / 'core.jar'
        jar.write_bytes(b'reviewed-current-entry-core')
        classes = root / 'classes'
        compiled = classes / 'io/github/ym0506/routecontract/consumer/CurrentEntrySuccessorProbe.class'
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(b'compiled-current-entry-probe')
        return {'classes': [str(classes)], 'compiledClasses': {str(compiled): self.sha(compiled.read_bytes())},
                'artifacts': [{'group': 'io.github.ym0506.routecontract', 'module': 'routecontract-core',
                               'path': str(jar), 'sha256': self.sha(jar.read_bytes())}]}

    def test_launch_rejects_changed_reviewed_jar_and_compiled_probe_independently(self):
        for changed in ('jar', 'class'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                graph = self.fixture_graph(root)
                paths = [graph['artifacts'][0]['path'], *graph['classes']]
                helper.verified_launch_inputs(paths, graph, [], root)
                target = Path(graph['artifacts'][0]['path'] if changed == 'jar'
                              else next(iter(graph['compiledClasses'])))
                target.write_bytes(b'replaced-after-review')
                with self.assertRaises(helper.RuntimeAcceptanceError):
                    helper.verified_launch_inputs(paths, graph, [], root)

    def test_unreviewed_classpath_or_product_class_in_probe_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = self.fixture_graph(root)
            paths = [graph['artifacts'][0]['path'], *graph['classes']]
            unreviewed = root / 'unreviewed.jar'
            unreviewed.write_bytes(b'unreviewed')
            with self.assertRaises(helper.RuntimeAcceptanceError):
                helper.verified_launch_inputs([*paths, str(unreviewed)], graph, [], root)
            shadow = root / 'classes/io/github/ym0506/routecontract/api/RouteContract.class'
            shadow.parent.mkdir(parents=True)
            shadow.write_bytes(b'fake-production-entry')
            with self.assertRaises(helper.RuntimeAcceptanceError):
                helper.verified_launch_inputs(paths, graph, [], root)

    def test_source_fingerprint_change_rejects_execution_even_with_unchanged_reviewed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'reviewed-receipt.json'
            receipt.write_text('{"candidate":"reviewed"}\n')
            pin = self.sha(receipt.read_bytes())
            initial = {'probe.java': self.sha(b'reviewed-source')}
            with patch.object(helper, 'fingerprint_inputs', return_value=initial):
                helper.assert_unchanged_inputs(initial, receipt, pin)
            with patch.object(helper, 'fingerprint_inputs', return_value={'probe.java': self.sha(b'replaced-source')}):
                with self.assertRaises(helper.RuntimeAcceptanceError):
                    helper.assert_unchanged_inputs(initial, receipt, pin)

    def test_receipt_replacement_rejects_execution_even_with_unchanged_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'reviewed-receipt.json'
            receipt.write_text('{"candidate":"reviewed"}\n')
            pin = self.sha(receipt.read_bytes())
            initial = {'probe.java': self.sha(b'reviewed-source')}
            receipt.write_text('{"candidate":"different"}\n')
            with patch.object(helper, 'fingerprint_inputs', return_value=initial):
                with self.assertRaises(helper.RuntimeAcceptanceError):
                    helper.assert_unchanged_inputs(initial, receipt, pin)


if __name__ == '__main__':
    unittest.main()
