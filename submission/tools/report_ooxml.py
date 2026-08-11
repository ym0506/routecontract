"""Dependency-free OOXML helpers shared by the report builder and its tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


WORDPROCESSINGML_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def mark_row_cannot_split(row: Any) -> None:
    """Add an idempotent w:cantSplit rule to a python-docx or XML table row."""
    element = getattr(row, "_tr", row)
    tr_pr_tag = f"{{{WORDPROCESSINGML_NAMESPACE}}}trPr"
    cant_split_tag = f"{{{WORDPROCESSINGML_NAMESPACE}}}cantSplit"
    tr_pr = element.find(tr_pr_tag)
    if tr_pr is None:
        tr_pr = element.makeelement(tr_pr_tag, {})
        element.insert(0, tr_pr)
    if tr_pr.find(cant_split_tag) is None:
        tr_pr.append(element.makeelement(cant_split_tag, {}))


def mark_data_rows_cannot_split(rows: Iterable[Any]) -> None:
    for row in rows:
        mark_row_cannot_split(row)
