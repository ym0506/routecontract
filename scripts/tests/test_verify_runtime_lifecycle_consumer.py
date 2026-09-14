from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('runtime_lifecycle_test', ROOT / 'scripts/verify-runtime-lifecycle-consumer.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


def observation(case):
    positive = case['row'] == 'A12'
    return {'formatVersion': 1, 'caseId': case['caseId'], 'runtime': case['runtime'],
            'outcome': 'CAPTURED' if positive else 'EXPECTED_REJECTION',
            'diagnosticCode': None if positive else case['expected'],
            'actionCount': 1 if positive else 0, 'driverExecutionCount': 1 if positive else 0,
            'returnedSnapshot': positive, 'captureStatus': 'COMPLETE' if positive else None,
            'observedPhysicalAttemptCount': 1 if positive else 0, 'exactBusinessRowsMatched': positive,
            'topLevelThrowableClass': None if positive else 'java.lang.IllegalStateException',
            'exposedRawLinkageError': False,
            'semanticChecks': {key: True for key in (*helper.COMMON_CHECKS, *helper.CASE_CHECKS[case['row']])},
            'loaderPhases': [{'phase': 'before', 'loader': 'actual-inventory-1'},
                             {'phase': 'after', 'loader': 'actual-inventory-2'}]}


class RuntimeLifecycleAcceptanceTest(unittest.TestCase):
    def test_plan_is_only_the_three_existing_rows_for_both_exact_runtimes(self):
        cases = helper.case_plan()
        self.assertEqual(6, len(cases))
        self.assertEqual({(row, runtime) for row in ('A11', 'A12', 'A13') for runtime in ('5.5.2', '5.5.3')},
                         {(case['row'], case['runtime']) for case in cases})
        self.assertEqual(6, len({case['caseId'] for case in cases}))

    def test_supported_observations_are_classified_for_each_cell(self):
        for case in helper.case_plan():
            with self.subTest(case=case['caseId']):
                self.assertEqual('PASS', helper.classify(case, observation(case)))

    def test_setup_failure_cannot_pass_using_a_plausible_negative_report(self):
        case = helper.case_plan()[0]
        self.assertEqual('PROCESS_FAILED', helper.evaluate_process(case, 1, observation(case), ''))
        self.assertEqual('PROCESS_TIMEOUT', helper.evaluate_process(case, 0, observation(case), '', True))
        for report in (None, [], 'RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE'):
            self.assertEqual('MISSING_OR_MALFORMED_RESULT', helper.evaluate_process(case, 0, report, ''))

    def test_actual_a12_shutdown_tail_overrides_exit_zero_and_captured_report(self):
        # Exact non-sensitive tail from the first frozen A12-552 run: two shutdown threads
        # interleaved their output after the CAPTURED report and still left process exit 0.
        log = '''ROUTECONTRACT_LIFECYCLE A12-552 CAPTURED
Exception in thread "Thread-3" Exception in thread "Thread-5" java.lang.NoClassDefFoundError: org/testcontainers/utility/PathUtils
\tat lifecycle-application//org.testcontainers.utility.MountableFile.lambda$deleteOnExit$0(MountableFile.java:318)
\tat java.base/java.lang.Thread.run(Thread.java:840)
Caused by: java.lang.ClassNotFoundException: org.testcontainers.utility.PathUtils
\tat java.base/java.net.URLClassLoader.findClass(URLClassLoader.java:445)
'''
        case = helper.case_plan()[1]
        self.assertEqual('PASS', helper.classify(case, observation(case)))
        self.assertEqual('UNCAUGHT_JVM_THROWABLE', helper.evaluate_process(case, 0, observation(case), log))
        self.assertEqual(1, len(helper.uncaught_thread_failures(log)))

    def test_shutdown_exception_fails_any_cell_while_normal_warning_does_not(self):
        for case in helper.case_plan():
            log = ('[main] WARN HikariConfig - pool warning\n'
                   f'ROUTECONTRACT_LIFECYCLE {case["caseId"]} {observation(case)["outcome"]}\n')
            self.assertEqual('PASS', helper.evaluate_process(case, 0, observation(case), log))
            for kind in ('java.lang.NoClassDefFoundError', 'java.lang.IllegalStateException'):
                failure = log + f'Exception in thread "shutdown-cleanup" {kind}: cleanup failed\n'
                self.assertEqual('UNCAUGHT_JVM_THROWABLE',
                                 helper.evaluate_process(case, 0, observation(case), failure))

    def test_stale_report_from_another_case_or_runtime_is_rejected(self):
        case = helper.case_plan()[0]
        for changes in ({'caseId': 'A11-553'}, {'runtime': '5.5.3'}, {'formatVersion': 0}):
            self.assertEqual('WRONG_CASE_IDENTITY', helper.classify(case, dict(observation(case), **changes)))

    def test_every_loader_claim_must_be_measured_and_true(self):
        for case in helper.case_plan():
            for key in (*helper.COMMON_CHECKS, *helper.CASE_CHECKS[case['row']]):
                for value in (False, None, 'true', 1):
                    observed = observation(case)
                    observed['semanticChecks'][key] = value
                    self.assertEqual('LOADER_SEMANTICS_NOT_PROVEN', helper.classify(case, observed), (case, key, value))
            observed = observation(case)
            observed.pop('semanticChecks')
            self.assertEqual('LOADER_SEMANTICS_NOT_PROVEN', helper.classify(case, observed))
            for malformed in (None, [], 'all passed', True):
                self.assertEqual('LOADER_SEMANTICS_NOT_PROVEN', helper.classify(
                    case, dict(observation(case), semanticChecks=malformed)))

    def test_loader_assertions_do_not_replace_raw_before_after_inventory(self):
        case = helper.case_plan()[1]
        for phases in (None, [], [{}], [{}, {}], ['before', 'after']):
            self.assertEqual('MISSING_RAW_LOADER_EVIDENCE',
                             helper.classify(case, dict(observation(case), loaderPhases=phases)))

    def test_negative_never_hides_an_action_empty_complete_or_linkage_error(self):
        for case in [c for c in helper.case_plan() if c['row'] != 'A12']:
            for changes in ({'actionCount': 1}, {'driverExecutionCount': 1}, {'returnedSnapshot': True},
                            {'captureStatus': 'COMPLETE'}, {'observedPhysicalAttemptCount': 1},
                            {'diagnosticCode': 'RC_LEGACY_ADAPTER_COLLISION'},
                            {'topLevelThrowableClass': 'java.util.ServiceConfigurationError'}):
                self.assertEqual('WRONG_BUSINESS_OR_CAPTURE_RESULT',
                                 helper.classify(case, dict(observation(case), **changes)))
            self.assertEqual('RAW_LINKAGE_OR_MISSING_EVIDENCE',
                             helper.classify(case, dict(observation(case), exposedRawLinkageError=True)))

    def test_mysql_business_result_and_driver_count_are_independent_of_complete_capture(self):
        case = helper.case_plan()[1]
        for changes in ({'exactBusinessRowsMatched': False}, {'driverExecutionCount': 0},
                        {'driverExecutionCount': 2}, {'observedPhysicalAttemptCount': 0},
                        {'actionCount': 0}, {'captureStatus': 'INCOMPLETE'}, {'returnedSnapshot': False},
                        {'topLevelThrowableClass': 'java.sql.SQLException'}, {'outcome': 'FAILED'}):
            self.assertEqual('WRONG_BUSINESS_OR_CAPTURE_RESULT',
                             helper.classify(case, dict(observation(case), **changes)))
        for field in ('actionCount', 'driverExecutionCount', 'observedPhysicalAttemptCount'):
            self.assertEqual('WRONG_BUSINESS_OR_CAPTURE_RESULT',
                             helper.classify(case, dict(observation(case), **{field: True})))

    def test_partial_duplicate_or_failed_cases_cannot_complete_the_matrix(self):
        results = [{'case': case, 'outcome': 'PASS'} for case in helper.case_plan()]
        self.assertTrue(helper.complete_matrix(results))
        self.assertFalse(helper.complete_matrix([]))
        self.assertFalse(helper.complete_matrix(results[:3]))
        self.assertFalse(helper.complete_matrix([*results[:5], results[0]]))
        broken = copy.deepcopy(results)
        broken[5]['outcome'] = 'PROCESS_FAILED'
        self.assertFalse(helper.complete_matrix(broken))

    def test_receipt_requires_external_hash_even_for_structurally_valid_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            artifacts = []
            for module in ('routecontract-core', 'routecontract-shardingsphere-5.5', 'routecontract-shardingsphere-5.5.2'):
                for extension in ('jar', 'pom', 'module'):
                    name = f'{module}-0.2.0.{extension}'
                    artifacts.append({'module': module, 'name': name,
                                      'relativePath': f'io/github/ym0506/routecontract/{module}/0.2.0/{name}',
                                      'sha256': 'a' * 64})
            path.write_text(json.dumps({'formatVersion': 1, 'routeContractVersion': '0.2.0', 'artifacts': artifacts}))
            expected = helper.digest(path.read_bytes())
            self.assertEqual(9, len(helper.pinned_receipt(path, expected)[0]['artifacts']))
            for wrong in ('', 'z' * 64, '0' * 64):
                with self.assertRaises(helper.LifecycleError):
                    helper.pinned_receipt(path, wrong)
            path.write_text(path.read_text() + '\n')
            with self.assertRaises(helper.LifecycleError):
                helper.pinned_receipt(path, expected)

    def test_graph_rejects_wrong_runtime_or_first_party_bytes_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = []
            pins = []
            for group, module, version in ((helper.GROUP, 'routecontract-core', '0.2.0'),
                                           (helper.GROUP, helper.ADAPTERS['5.5.2'], '0.2.0'),
                                           ('org.apache.shardingsphere', 'shardingsphere-infra-executor', '5.5.2')):
                path = root / f'{module}.jar'
                path.write_bytes(module.encode())
                pin = helper.digest(path.read_bytes())
                artifacts.append({'group': group, 'module': module, 'version': version,
                                  'path': str(path), 'sha256': pin})
                if group == helper.GROUP:
                    pins.append({'module': module, 'name': path.name, 'sha256': pin})
            graph = {'runtime': '5.5.2', 'artifacts': artifacts, 'compileArtifacts': artifacts}
            receipt = {'artifacts': pins}
            helper.verify_graph(graph, '5.5.2', receipt)
            for field, mutation in (('runtime', '5.5.3'), ('artifacts', artifacts[:1])):
                with self.assertRaises(helper.LifecycleError):
                    helper.verify_graph(dict(graph, **{field: mutation}), '5.5.2', receipt)
            bad = copy.deepcopy(graph)
            bad['compileArtifacts'][-1]['version'] = '5.5.3'
            with self.assertRaises(helper.LifecycleError):
                helper.verify_graph(bad, '5.5.2', receipt)
            Path(artifacts[0]['path']).write_bytes(b'changed')
            with self.assertRaises(helper.LifecycleError):
                helper.verify_graph(graph, '5.5.2', receipt)

    def test_launcher_class_directory_cannot_shadow_production_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / 'io/github/ym0506/routecontract/lifecycle/RuntimeLifecycleProbe.class'
            fixture.parent.mkdir(parents=True)
            fixture.write_bytes(b'fixture')
            self.assertEqual(1, len(helper.class_hashes([directory])))
            production = root / 'io/github/ym0506/routecontract/api/RouteContract.class'
            production.parent.mkdir(parents=True)
            production.write_bytes(b'fake production')
            with self.assertRaises(helper.LifecycleError):
                helper.class_hashes([directory])


if __name__ == '__main__':
    unittest.main()
