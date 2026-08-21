from __future__ import annotations

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "report_ooxml.py"
SPEC = importlib.util.spec_from_file_location("report_ooxml", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report_ooxml = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_ooxml)

W = report_ooxml.WORDPROCESSINGML_NAMESPACE


class AttachmentRowPaginationTest(unittest.TestCase):
    def test_marks_every_data_row_cannot_split_and_is_idempotent(self) -> None:
        table = ET.fromstring(
            f"""
            <w:tbl xmlns:w="{W}">
              <w:tr><w:trPr><w:tblHeader/></w:trPr></w:tr>
              <w:tr><w:tc/></w:tr>
              <w:tr><w:trPr/></w:tr>
            </w:tbl>
            """
        )
        rows = table.findall(f"{{{W}}}tr")

        report_ooxml.mark_data_rows_cannot_split(rows[1:])
        report_ooxml.mark_data_rows_cannot_split(rows[1:])

        self.assertEqual([], rows[0].findall(f"{{{W}}}trPr/{{{W}}}cantSplit"))
        for row in rows[1:]:
            with self.subTest(row=ET.tostring(row, encoding="unicode")):
                self.assertEqual(
                    1,
                    len(row.findall(f"{{{W}}}trPr/{{{W}}}cantSplit")),
                )
                self.assertEqual(f"{{{W}}}trPr", row[0].tag)


if __name__ == "__main__":
    unittest.main()
