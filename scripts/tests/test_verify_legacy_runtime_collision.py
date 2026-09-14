from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('a28_runtime_test', ROOT / 'scripts/verify-legacy-runtime-collision.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


class LegacyRuntimeAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.case = {'mode': 'capture', 'expected': 'RC_LEGACY_ADAPTER_COLLISION'}
        self.observed = {'returned': False, 'actionEntered': False, 'physicalBusinessExecutions': 0,
                         'businessRows': [], 'exceptionClasses': ['java.lang.IllegalStateException'],
                         'exceptionMessages': ['RC_LEGACY_ADAPTER_COLLISION: actual collision'], 'linkageFailure': False}

    def test_matrix_executes_every_real_distributed_rc_and_stable_input(self):
        registry = helper.load_registry(helper.REGISTRY)
        cases = helper.cases(registry)
        self.assertEqual(36, len(cases))
        self.assertEqual(36, len({case['id'] for case in cases}))
        self.assertEqual(4, sum(case['legacy'] is None for case in cases))
        for legacy in ('0.1.0', '0.1.2', '0.1.3', '0.1.0-rc2'):
            rows = [case for case in cases if case['legacy'] == legacy]
            self.assertEqual(8, len(rows))
            self.assertEqual({(runtime, order, mode) for runtime in ('5.5.2', '5.5.3')
                              for order in ('legacy-first', 'legacy-last') for mode in ('capture', 'sql')},
                             {(case['runtime'], case['order'], case['mode']) for case in rows})

    def test_real_collision_diagnostic_is_required(self):
        self.assertEqual('PASS', helper.classify(self.case, self.observed))
        self.observed['exceptionMessages'] = ['RouteContract supports exactly Apache ShardingSphere 5.5.3']
        self.assertEqual('WRONG_DIAGNOSTIC', helper.classify(self.case, self.observed))

    def test_expected_code_cannot_hide_an_action_or_physical_execution(self):
        for field, value in [('actionEntered', True), ('physicalBusinessExecutions', 1), ('businessRows', ['201:3:PAID'])]:
            observed = dict(self.observed, **{field: value})
            self.assertEqual('ACTION_OR_SQL_EXECUTED', helper.classify(self.case, observed))

    def test_expected_code_cannot_hide_linkage_or_silent_success(self):
        self.assertEqual('LINKAGE_FAILURE', helper.classify(self.case, dict(self.observed, linkageFailure=True)))
        self.assertEqual('SILENT_SUCCESS', helper.classify(self.case, dict(self.observed, returned=True)))

    def test_business_control_checks_values_and_real_execution_separately(self):
        case = {'mode': 'sql', 'expected': 'CLEAN_SUCCESS'}
        observed = dict(self.observed, returned=True, exceptionClasses=[], exceptionMessages=[],
                        physicalBusinessExecutions=1, businessRows=['201:3:PAID'])
        self.assertEqual('PASS', helper.classify(case, observed))
        for changes in ({'businessRows': ['202:2:PAID']}, {'physicalBusinessExecutions': 0}, {'actionEntered': True}):
            self.assertEqual('CONTROL_FAILED', helper.classify(case, dict(observed, **changes)))

    def test_manual_order_really_places_legacy_before_or_after_current_jars(self):
        graph = {'classes': ['/fixture/classes'], 'artifacts': [
            {'group': helper.GROUP, 'module': 'routecontract-core', 'path': '/core.jar'},
            {'group': helper.GROUP, 'module': 'adapter', 'path': '/adapter.jar'},
            {'group': 'thirdparty', 'module': 'jdbc', 'path': '/jdbc.jar'}]}
        inventory = [{'origin': 'public-legacy', 'version': '0.1.3', 'name': 'legacy.jar', 'relativePath': 'legacy.jar'}]
        case = {'legacy': '0.1.3', 'order': 'legacy-first'}
        first = helper.assemble_classpath(case, graph, inventory, Path('/repo'))
        last = helper.assemble_classpath(dict(case, order='legacy-last'), graph, inventory, Path('/repo'))
        self.assertEqual(['/repo/legacy.jar', '/adapter.jar', '/core.jar'], first[:3])
        self.assertEqual(['/adapter.jar', '/core.jar', '/repo/legacy.jar'], last[:3])
        self.assertEqual(first[3:], last[3:])

    def test_capture_control_requires_the_no_start_snapshot(self):
        case = {'mode': 'capture', 'expected': 'CLEAN_SUCCESS'}
        observed = dict(self.observed, returned=True, actionEntered=True, exceptionClasses=[], exceptionMessages=[])
        self.assertEqual('CONTROL_FAILED', helper.classify(case, observed))
        observed['captureSnapshot'] = {'status': 'INCOMPLETE', 'observedPhysicalAttemptCount': 0,
                                       'collectorDiagnostics': ['RC_NO_START_CALLBACK_OBSERVED']}
        self.assertEqual('PASS', helper.classify(case, observed))
        observed['captureSnapshot']['observedPhysicalAttemptCount'] = 1
        self.assertEqual('CONTROL_FAILED', helper.classify(case, observed))

    def fixture_graph(self, root):
        jar = root / 'core.jar'
        jar.write_bytes(b'reviewed-runtime-byte-fixture')
        directory = root / 'classes'
        compiled = directory / 'io/github/ym0506/routecontract/consumer/Probe.class'
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(b'compiled-probe-byte-fixture')
        return {'classes': [str(directory)], 'compiledClasses': helper.class_hashes([str(directory)]),
                'artifacts': [{'group': helper.GROUP, 'module': 'routecontract-core', 'path': str(jar),
                               'sha256': helper.digest(jar.read_bytes())}]}

    def test_launch_rejects_changed_runtime_cache_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = self.fixture_graph(root)
            paths = [graph['artifacts'][0]['path'], *graph['classes']]
            helper.verified_launch_inputs(paths, graph, [], root)
            (root / 'core.jar').write_bytes(b'changed')
            with self.assertRaisesRegex(helper.RuntimeAcceptanceError, 'differs'):
                helper.verified_launch_inputs(paths, graph, [], root)

    def test_launch_rejects_changed_or_production_fixture_classes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = self.fixture_graph(root)
            paths = [graph['artifacts'][0]['path'], *graph['classes']]
            compiled = Path(next(iter(graph['compiledClasses'])))
            compiled.write_bytes(b'changed')
            with self.assertRaisesRegex(helper.RuntimeAcceptanceError, 'consumer bytes changed'):
                helper.verified_launch_inputs(paths, graph, [], root)
            compiled.with_name('Probe.class').parent.parent.joinpath('RouteContract.class').write_bytes(b'production shadow')
            with self.assertRaisesRegex(helper.RuntimeAcceptanceError, 'Unexpected production'):
                helper.class_hashes(graph['classes'])

    def test_process_exit_and_timeout_each_retain_local_case_result(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                graph = self.fixture_graph(root)
                case = {'id': 'control', 'runtime': '5.5.3', 'mode': 'capture', 'legacy': None,
                        'order': None, 'expected': 'CLEAN_SUCCESS'}
                failure = subprocess.TimeoutExpired(['java'], 180) if timeout else None
                with patch.object(helper.subprocess, 'run', side_effect=failure,
                                  return_value=subprocess.CompletedProcess(['java'], 42)):
                    result = helper.run_case(case, root, graph, [], root, Path('/java'), {}, 0)
                self.assertEqual('PROCESS_TIMEOUT' if timeout else 'PROCESS_FAILED', result['outcome'])
                self.assertTrue((root / 'cases/control/result.json').is_file())
                self.assertEqual(helper.digest(b''), result['logSha256'])


if __name__ == '__main__':
    unittest.main()
