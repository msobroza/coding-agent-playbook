# mypy: ignore-errors
"""Snapshot-style tests so a refactor that preserves behavior keeps them green.

The agent should not modify this file — the refactor's contract is that the
public output is byte-identical before and after the extraction.

The ``# mypy: ignore-errors`` pragma at the top of the file silences the
engine repo's mypy gate so this fixture can ship as an authoring artifact
without the engine treating it as a first-class module. The eval runner copies
the file into a scratch repo whose own mypy config will be the real check.
"""

from src.report import render_report


def test_render_report_empty_rows() -> None:
    out = render_report("Empty", [])
    assert out.startswith("# Empty")
    assert "count:    0" in out
    assert "total:    0" in out


def test_render_report_single_row() -> None:
    out = render_report("Single", [("alpha", 10)])
    assert "- alpha: 10" in out
    assert "count:    1" in out
    assert "total:    10" in out
    assert "average:  10.00" in out


def test_render_report_multiple_rows() -> None:
    out = render_report("Multi", [("alpha", 10), ("bravo-bravo", 20), ("c", 30)])
    assert "## Totals" in out
    assert "count:    3" in out
    assert "total:    60" in out
    assert "average:  20.00" in out
    assert "widest label" in out
