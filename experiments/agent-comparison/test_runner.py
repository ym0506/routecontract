"""Validate that a green process alone cannot become a successful JUnit receipt."""
from pathlib import Path
import tempfile
import unittest

from run import ARCHIVE_BYTES, ComparisonError, junit_counts, prepare_agent


CONSOLE_RESULT = b"""
[         1 tests found           ]
[         0 tests skipped         ]
[         1 tests started         ]
[         0 tests aborted         ]
[         1 tests successful      ]
[         0 tests failed          ]
"""


class ConsoleResultTest(unittest.TestCase):
    def test_accepts_exactly_one_executed_test(self):
        self.assertEqual(1, junit_counts(CONSOLE_RESULT)["successful"])

    def test_rejects_empty_skipped_failed_or_duplicate_result(self):
        inputs = [b"", CONSOLE_RESULT + CONSOLE_RESULT,
                  CONSOLE_RESULT.replace(b"0 tests skipped", b"1 tests skipped"),
                  CONSOLE_RESULT.replace(b"1 tests started", b"0 tests started"),
                  CONSOLE_RESULT.replace(b"0 tests failed", b"1 tests failed")]
        for output in inputs:
            with self.subTest(outputLength=len(output)), self.assertRaises(ComparisonError):
                junit_counts(output)

    def test_equal_size_modified_archive_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "wrong.tar.gz"
            with archive.open("wb") as stream:
                stream.truncate(ARCHIVE_BYTES)
            with self.assertRaises(ComparisonError) as caught:
                prepare_agent(archive, root / "extracted")
            self.assertEqual("ARCHIVE_DIGEST", caught.exception.code)
            self.assertFalse((root / "extracted").exists())


if __name__ == "__main__":
    unittest.main()
