"""Stdlib ``xml.etree`` parser for junit XML (SPEC prM §B2, Track M4).

``pytest --junitxml=…`` emits a standard junit document; this module reduces it
to a :class:`JunitSummary` (``passed/failed/errors/skipped/total``) with **no new
dependency**. It accepts both root shapes pytest can produce: a ``<testsuites>``
wrapper holding one or more ``<testsuite>`` elements, or a single bare
``<testsuite>`` root.

Counting: ``total`` is the number of ``<testcase>`` elements; a case is a
*failure* if it carries a ``<failure>`` child, an *error* if it carries an
``<error>`` child, and *skipped* if it carries a ``<skipped>`` child (a case may
appear in at most one of those three buckets - failure wins over error wins over
skipped, matching pytest's exclusive outcome). ``passed`` is whatever is left.
Both failures and errors count *against* the pass rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class JunitSummary:
    """Reduced junit counts for one test run.

    ``passed + failed + errors + skipped == total`` always holds (the buckets are
    mutually exclusive). :meth:`pass_rate` is the SCORE the ``test_pass_rate``
    evaluator surfaces.
    """

    passed: int
    failed: int
    errors: int
    skipped: int
    total: int

    def pass_rate(self) -> float:
        """``passed / (total - skipped)`` - the documented test-pass SCORE.

        Skips are excluded from the denominator (a skipped test is neither a
        pass nor a failure). A suite with no *runnable* tests (every test
        skipped, or an empty suite) yields ``1.0`` rather than ``0/0`` - there is
        nothing failing, so the gate must not breach.
        """
        runnable = self.total - self.skipped
        if runnable <= 0:
            return 1.0
        return self.passed / runnable


def _iter_testcases(root: ET.Element) -> list[ET.Element]:
    """Every ``<testcase>`` under ``root`` regardless of the wrapper shape."""
    if root.tag == "testcase":
        return [root]
    return list(root.iter("testcase"))


def parse_junit_xml(text: str) -> JunitSummary:
    """Parse a junit XML *string* into a :class:`JunitSummary`.

    Counts are derived from the ``<testcase>`` elements themselves (not the
    summary attributes on ``<testsuite>``) so the buckets stay mutually exclusive
    and consistent across pytest versions. Raises
    :class:`xml.etree.ElementTree.ParseError` on malformed XML (the caller
    decides how to surface it).
    """
    root = ET.fromstring(text)
    cases = _iter_testcases(root)

    failed = errors = skipped = 0
    for case in cases:
        if case.find("failure") is not None:
            failed += 1
        elif case.find("error") is not None:
            errors += 1
        elif case.find("skipped") is not None:
            skipped += 1
    total = len(cases)
    passed = total - failed - errors - skipped
    return JunitSummary(
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        total=total,
    )
