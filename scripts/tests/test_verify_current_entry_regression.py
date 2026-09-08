from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('current_entry_regression_test',
                                             ROOT / 'scripts/verify-current-entry-regression.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


class CurrentEntryRegressionTest(unittest.TestCase):
    def setUp(self):
        self.core = Path('/new-core.jar')
        self.case = {'id': 'focused', 'mode': 'capture', 'legacyPath': '/legacy.jar'}
        self.observed = {'mode': 'capture', 'pid': 17, 'javaVersion': '17.0.15',
                         'shardingSphereVersion': '5.5.2', 'returned': False, 'actionEntered': False,
                         'actionEntries': 0, 'linkageFailure': False,
                         'exceptionClasses': ['java.lang.IllegalStateException'],
                         'exceptionMessages': ['RC_LEGACY_ADAPTER_COLLISION: remove legacy dependency'],
                         'stackFrames': ['io.github.ym0506.routecontract.internal.CurrentRuntimeGuard.verify'],
                         'newEntryOrigin': '/new-core.jar', 'guardOrigin': '/new-core.jar',
                         'legacyEntryOrigin': '/legacy.jar', 'captureRegistryOrigin': '/legacy.jar'}

    def test_real_new_guard_and_exact_execution_environment_are_required(self):
        self.assertEqual('PASS', helper.classify(self.case, self.observed, self.core))
        for changes, expected in [({'exceptionMessages': ['RouteContract supports exactly 5.5.3']}, 'WRONG_DIAGNOSTIC'),
                                  ({'stackFrames': ['fixture.SyntheticGuard.verify']}, 'GUARD_NOT_OBSERVED'),
                                  ({'javaVersion': '21.0.11'}, 'WRONG_EXECUTION_ENVIRONMENT'),
                                  ({'shardingSphereVersion': '5.5.3'}, 'WRONG_EXECUTION_ENVIRONMENT'),
                                  ({'mode': 'captureResult'}, 'WRONG_EXECUTION_ENVIRONMENT')]:
            with self.subTest(changes=changes):
                self.assertEqual(expected, helper.classify(self.case, dict(self.observed, **changes), self.core))

    def test_marker_cannot_hide_action_linkage_silent_success_or_wrong_origin(self):
        for changes, expected in [({'actionEntered': True}, 'ACTION_ENTERED'),
                                  ({'actionEntries': 1}, 'ACTION_ENTERED'),
                                  ({'returned': True}, 'SILENT_SUCCESS'),
                                  ({'linkageFailure': True}, 'LINKAGE_FAILURE'),
                                  ({'newEntryOrigin': '/legacy.jar'}, 'UNEXPECTED_CLASS_ORIGIN'),
                                  ({'guardOrigin': '/other-core.jar'}, 'UNEXPECTED_CLASS_ORIGIN'),
                                  ({'captureRegistryOrigin': '/new-core.jar'}, 'UNEXPECTED_CLASS_ORIGIN'),
                                  ({'legacyEntryOrigin': '/new-core.jar'}, 'UNEXPECTED_CLASS_ORIGIN')]:
            with self.subTest(changes=changes):
                self.assertEqual(expected, helper.classify(self.case, dict(self.observed, **changes), self.core))

    def test_incomplete_observation_is_not_a_pass(self):
        for field in self.observed:
            observed = dict(self.observed)
            del observed[field]
            self.assertEqual('MALFORMED_OBSERVATION', helper.classify(self.case, observed, self.core))

    def test_compiled_probe_cannot_shadow_product_or_include_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / 'io/github/ym0506/routecontract/consumer/Probe.class'
            valid.parent.mkdir(parents=True)
            valid.write_bytes(b'fixture-bytecode')
            prefix = 'io/github/ym0506/routecontract/consumer/'
            self.assertEqual(1, len(helper.class_hashes(root, prefix)))
            production = root / helper.NEW_CLASSES[0]
            production.parent.mkdir(parents=True)
            production.write_bytes(b'shadow-product')
            with self.assertRaisesRegex(helper.RegressionError, 'Unexpected non-probe'):
                helper.class_hashes(root, prefix)
            production.unlink()
            valid.with_name('resource.txt').write_text('not class output')
            with self.assertRaisesRegex(helper.RegressionError, 'Unexpected non-probe'):
                helper.class_hashes(root, prefix)

    def test_core_pin_and_compiler_output_equality_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            classes = root / 'classes'
            jar = root / 'core.jar'
            with zipfile.ZipFile(jar, 'w') as output:
                for name in helper.NEW_CLASSES:
                    content = name.encode()
                    output.writestr(name, content)
                    path = classes / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
            pin = helper.digest(jar.read_bytes())
            self.assertEqual(2, len(helper.verify_core(jar, pin, classes)['compiledClasses']))
            with self.assertRaisesRegex(helper.RegressionError, 'SHA-256'):
                helper.verify_core(jar, '0' * 64, classes)
            (classes / helper.NEW_CLASSES[0]).write_bytes(b'changed-class')
            with self.assertRaisesRegex(helper.RegressionError, 'compiler outputs'):
                helper.verify_core(jar, pin, classes)

    def test_input_pins_and_retained_containment_reject_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            retained = root / 'retained'
            retained.mkdir()
            artifact = retained / 'dependency.jar'
            artifact.write_bytes(b'original')
            pin = helper.file_pin(artifact)
            self.assertEqual(artifact.resolve(), helper.contained_file(artifact, retained))
            artifact.write_bytes(b'replaced')
            with self.assertRaisesRegex(helper.RegressionError, 'SHA-256'):
                helper.verify_pins([pin])
            outside = root / 'outside.jar'
            outside.write_bytes(b'outside')
            with self.assertRaisesRegex(helper.RegressionError, 'escapes'):
                helper.contained_file(outside, retained)
            link = retained / 'link.jar'
            link.symlink_to(outside)
            with self.assertRaisesRegex(helper.RegressionError, 'symbolic link'):
                helper.contained_file(link, retained)

    def test_process_failure_and_timeout_preserve_case_evidence(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                classes = directory / 'classes'
                compiled = classes / 'io/github/ym0506/routecontract/consumer/Probe.class'
                compiled.parent.mkdir(parents=True)
                compiled.write_bytes(b'probe')
                class_pins = helper.class_hashes(classes)
                error = subprocess.TimeoutExpired(['java'], 60) if timeout else None
                with patch.object(helper.subprocess, 'run', side_effect=error,
                                  return_value=subprocess.CompletedProcess(['java'], 42)):
                    result = helper.run_case(self.case, directory, Path('/java'), self.core, '/adapter.jar',
                                             [], classes, class_pins, [])
                self.assertEqual('PROCESS_TIMEOUT' if timeout else 'PROCESS_FAILED', result['outcome'])
                self.assertTrue((directory / 'cases/focused/command.json').is_file())
                self.assertTrue((directory / 'cases/focused/result.json').is_file())


if __name__ == '__main__':
    unittest.main()
