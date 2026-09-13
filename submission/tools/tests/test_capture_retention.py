import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    'capture_retention', Path(__file__).resolve().parents[3] / 'examples/observer-cost/retention/run.py')
RETENTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RETENTION)


class CaptureRetentionEvidenceTest(unittest.TestCase):
    def histogram(self, retained=False):
        values = [(10, 160, 'java.lang.Object')]
        if retained:
            values += [(16, 384, RETENTION.PREFIX + 'CapturedResult'),
                       (16, 1024, RETENTION.PREFIX + 'RouteSnapshot'),
                       (24, 1152, RETENTION.PREFIX + 'PhysicalExecutionAttempt')]
        rows = [f'{i}: {count} {size} {name}' for i, (count, size, name) in enumerate(values, 1)]
        return '\n'.join(['1234:', 'num #instances #bytes class name (module)', *rows,
                          f'Total {sum(v[0] for v in values)} {sum(v[1] for v in values)}'])

    def event(self):
        return {'event': 'checkpoint', 'phase': 'block-1', 'operations': 10000,
                'successes': 9000, 'exceptions': 500, 'errors': 500, 'workloadNanos': 100,
                'java': '17.0.15+0', 'publicJarSha256': RETENTION.JAR_HASH}

    def test_zero_counts_are_only_accepted_in_a_complete_histogram(self):
        result = RETENTION.parse_histogram(self.histogram())
        RETENTION.require_zero(result)
        self.assertEqual(160, result['totalLiveObjectBytes'])
        self.assertEqual(7, len(result['instances']))

    def test_retained_result_control_trips_the_same_zero_gate(self):
        result = RETENTION.parse_histogram(self.histogram(True))
        with self.assertRaises(ValueError):
            RETENTION.require_zero(result)
        self.assertEqual(16, result['instances'][RETENTION.PREFIX + 'CapturedResult'])
        self.assertEqual(24, result['instances'][RETENTION.PREFIX + 'PhysicalExecutionAttempt'])

    def test_truncated_empty_or_inconsistent_histogram_is_rejected(self):
        valid = self.histogram()
        for text in ('', 'Total 0 0', valid.split('Total')[0], valid.replace('Total 10 160', 'Total 10 161'),
                     valid + '\nTotal 10 160'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                RETENTION.parse_histogram(text)

    def test_any_of_the_seven_per_capture_classes_prevents_zero_result(self):
        for name in RETENTION.CLASSES:
            with self.subTest(name=name):
                result = RETENTION.parse_histogram(self.histogram())
                result['instances'][name] = 1
                with self.assertRaises(ValueError):
                    RETENTION.require_zero(result)

    def test_full_counters_and_identity_are_verified(self):
        RETENTION.check_checkpoint(self.event(), 'block-1', False)
        for key, value in (('operations', True), ('successes', 10000), ('exceptions', 0),
                           ('errors', 0), ('workloadNanos', 0), ('publicJarSha256', '0' * 64),
                           ('java', '21.0.11'), ('phase', 'block-2'), ('event', 'complete')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                RETENTION.check_checkpoint({**self.event(), key: value}, 'block-1', False)

    def test_smoke_cannot_satisfy_full_operation_count(self):
        event = {**self.event(), 'operations': 160, 'successes': 144, 'exceptions': 8, 'errors': 8}
        RETENTION.check_checkpoint(event, 'block-1', True)
        with self.assertRaises(ValueError):
            RETENTION.check_checkpoint(event, 'block-1', False)


if __name__ == '__main__':
    unittest.main()
