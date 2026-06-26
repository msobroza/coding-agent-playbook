"""Stdlib parser for the Cobertura ``coverage.xml`` coverage.py emits (M4).

``pytest --cov --cov-report=xml:…`` writes a Cobertura-style document; this
module reduces it to a :class:`CoverageReport` - a per-file line-coverage
**percentage** plus an overall total - using stdlib ``xml.etree`` (no new
dependency).

Per-file percentage comes from the actual ``<line>`` hit counts under each
``<class>`` (``covered / total * 100``); when a file lists no ``<line>`` elements
the parser falls back to its ``line-rate`` attribute. The overall ``total`` is
the root ``<coverage line-rate="…">`` attribute (as a percentage) when present,
else the aggregate over every line in the document. coverage.py keys ``<class>``
by ``filename`` (a path relative to the project root), which is what the
``coverage`` evaluator uses as its FILE scope key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class CoverageReport:
    """Per-file line coverage (%) plus the overall total (%)."""

    per_file: dict[str, float] = field(default_factory=dict)
    total: float = 0.0


def _line_counts(class_el: ET.Element) -> tuple[int, int]:
    """``(covered, total)`` line counts for one ``<class>`` element."""
    total = 0
    covered = 0
    for line in class_el.iter("line"):
        total += 1
        if int(line.get("hits", "0")) > 0:
            covered += 1
    return covered, total


def parse_coverage_xml(text: str) -> CoverageReport:
    """Parse a Cobertura coverage XML *string* into a :class:`CoverageReport`.

    Raises :class:`xml.etree.ElementTree.ParseError` on malformed XML.
    """
    root = ET.fromstring(text)

    per_file: dict[str, float] = {}
    agg_covered = 0
    agg_total = 0
    for class_el in root.iter("class"):
        filename = class_el.get("filename")
        if filename is None:
            continue
        covered, total = _line_counts(class_el)
        if total > 0:
            per_file[filename] = covered / total * 100.0
            agg_covered += covered
            agg_total += total
        else:
            # No <line> elements listed: fall back to the file's line-rate.
            rate = class_el.get("line-rate")
            per_file[filename] = float(rate) * 100.0 if rate is not None else 0.0

    root_rate = root.get("line-rate")
    if root_rate is not None:
        total_pct = float(root_rate) * 100.0
    elif agg_total > 0:
        total_pct = agg_covered / agg_total * 100.0
    else:
        total_pct = 0.0

    return CoverageReport(per_file=per_file, total=total_pct)
