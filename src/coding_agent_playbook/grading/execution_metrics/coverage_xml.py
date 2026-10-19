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

The same pass keeps each file's per-line hit counts (:attr:`CoverageReport.lines`)
and the ``<sources>`` roots, for ``diff_coverage`` (prK §F.1.1). In source mode
(``--cov=src``) coverage.py writes each ``filename`` relative to the ``<source>``
that holds it, so :func:`repo_relative` maps it back onto the repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class CoverageReport:
    """Per-file line coverage (%) plus the overall total (%).

    ``lines`` maps each ``filename`` to ``{line number: hits}`` for its
    executable lines; ``sources`` are the ``<sources><source>`` roots those
    names are relative to.

    Example::

        >>> CoverageReport(per_file={"a.py": 50.0}, lines={"a.py": {1: 1, 2: 0}}).lines["a.py"][2]
        0
    """

    per_file: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    lines: dict[str, dict[int, int]] = field(default_factory=dict)
    sources: tuple[str, ...] = ()


def _line_counts(class_el: ET.Element, hits_by_line: dict[int, int]) -> tuple[int, int]:
    """``(covered, total)`` line counts for one ``<class>``; fills ``hits_by_line`` too.

    Every ``<line>`` row counts toward the percentage, as it always has; only
    rows carrying a line ``number`` can say *which* line was hit.
    """
    total = 0
    covered = 0
    for line in class_el.iter("line"):
        hits = int(line.get("hits", "0"))
        total += 1
        if hits > 0:
            covered += 1
        number = line.get("number", "")
        if number.isdigit():
            hits_by_line[int(number)] = max(hits, hits_by_line.get(int(number), 0))
    return covered, total


def _sources(root: ET.Element) -> tuple[str, ...]:
    """The non-empty ``<source>`` texts, in document order."""
    texts = (source.text.strip() for source in root.iter("source") if source.text)
    return tuple(text for text in texts if text)


def parse_coverage_xml(text: str) -> CoverageReport:
    """Parse a Cobertura coverage XML *string* into a :class:`CoverageReport`.

    Raises :class:`xml.etree.ElementTree.ParseError` on malformed XML.

    Example::

        >>> parse_coverage_xml('<coverage line-rate="0.5"/>').total
        50.0
    """
    root = ET.fromstring(text)

    per_file: dict[str, float] = {}
    lines: dict[str, dict[int, int]] = {}
    agg_covered = 0
    agg_total = 0
    for class_el in root.iter("class"):
        filename = class_el.get("filename")
        if filename is None:
            continue
        covered, total = _line_counts(class_el, lines.setdefault(filename, {}))
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

    return CoverageReport(per_file=per_file, total=total_pct, lines=lines, sources=_sources(root))


def repo_relative(filename: str, sources: Sequence[str], root: Path) -> str | None:
    """The POSIX path under ``root`` that coverage.py's ``filename`` names; ``None`` outside it.

    ``filename`` is resolved against each ``<source>`` (a relative source is
    relative to ``root``; no sources means ``root`` itself). With several
    sources the one where the file exists wins. Both sides are resolved through
    symlinks, because coverage.py writes canonical paths (``/private/tmp`` on
    macOS) and ``root`` may not be.

    Example::

        >>> repo_relative("pkg/a.py", ["/repo/src"], Path("/repo"))  # doctest: +SKIP
        'src/pkg/a.py'
    """
    base = Path(os.path.realpath(root))
    bases = [base / source for source in sources] or [base]
    candidates = [Path(os.path.realpath(source / filename)) for source in bases]
    inside = [path for path in candidates if path.is_relative_to(base)]
    if not inside:
        return None
    chosen = next((path for path in inside if path.is_file()), inside[0])
    return chosen.relative_to(base).as_posix()
