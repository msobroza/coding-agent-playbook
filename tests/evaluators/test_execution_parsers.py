"""Tests for the stdlib XML parsers (junit + Cobertura coverage) — PR-M M4.

The execution evaluators add **no playbook dependency**: they shell out to the
target's ``pytest``/``pytest-cov`` and parse the standard junit + coverage XML
with stdlib ``xml.etree``. These tests pin the parser contracts directly on small
hand-written XML fixtures (no subprocess), so they are fast and isolated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.execution.coverage_xml import (
    CoverageReport,
    parse_coverage_xml,
    repo_relative,
)
from coding_agent_playbook.evaluators.execution.junit import (
    JunitSummary,
    parse_junit_xml,
)

if TYPE_CHECKING:
    from pathlib import Path

# --------------------------------------------------------------------------- #
# junit
# --------------------------------------------------------------------------- #

_JUNIT_TESTSUITES = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="5" failures="1" errors="1" skipped="1">
    <testcase classname="t" name="ok1"/>
    <testcase classname="t" name="ok2"/>
    <testcase classname="t" name="boom"><failure message="x">trace</failure></testcase>
    <testcase classname="t" name="err"><error message="y">trace</error></testcase>
    <testcase classname="t" name="skip"><skipped/></testcase>
  </testsuite>
</testsuites>
"""

_JUNIT_SINGLE_SUITE = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="2" failures="0" errors="0" skipped="0">
  <testcase classname="t" name="a"/>
  <testcase classname="t" name="b"/>
</testsuite>
"""


def test_parse_junit_testsuites_counts() -> None:
    summary = parse_junit_xml(_JUNIT_TESTSUITES)
    assert isinstance(summary, JunitSummary)
    assert summary.total == 5
    assert summary.failed == 1
    assert summary.errors == 1
    assert summary.skipped == 1
    # passed = total - failed - errors - skipped
    assert summary.passed == 2


def test_parse_junit_single_testsuite_root() -> None:
    summary = parse_junit_xml(_JUNIT_SINGLE_SUITE)
    assert summary.total == 2
    assert summary.passed == 2
    assert summary.failed == 0
    assert summary.errors == 0
    assert summary.skipped == 0


def test_junit_pass_rate_excludes_skips() -> None:
    """Pass rate's denominator is total minus skips (documented semantics)."""
    summary = parse_junit_xml(_JUNIT_TESTSUITES)
    # 2 passed / (5 total - 1 skipped) = 2/4 = 0.5
    assert summary.pass_rate() == 0.5


def test_junit_pass_rate_all_skipped_is_one() -> None:
    """An all-skipped suite has no runnable tests; pass rate is 1.0 (vacuous)."""
    xml = (
        '<testsuite tests="1" failures="0" errors="0" skipped="1">'
        '<testcase name="s"><skipped/></testcase></testsuite>'
    )
    summary = parse_junit_xml(xml)
    assert summary.pass_rate() == 1.0


def test_junit_empty_suite_pass_rate_is_one() -> None:
    summary = parse_junit_xml('<testsuite tests="0"></testsuite>')
    assert summary.total == 0
    assert summary.pass_rate() == 1.0


def test_junit_bare_testcase_root() -> None:
    """A document whose root *is* a single ``<testcase>`` counts as one case."""
    summary = parse_junit_xml('<testcase classname="t" name="solo"/>')
    assert summary.total == 1
    assert summary.passed == 1


# --------------------------------------------------------------------------- #
# coverage (Cobertura, as coverage.py emits)
# --------------------------------------------------------------------------- #

_COVERAGE_XML = """\
<?xml version="1.0" ?>
<coverage line-rate="0.75" version="7.0">
  <packages>
    <package name="pkg" line-rate="0.75">
      <classes>
        <class filename="pkg/a.py" line-rate="1.0">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="1"/>
          </lines>
        </class>
        <class filename="pkg/b.py" line-rate="0.5">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


def test_parse_coverage_per_file_and_total() -> None:
    report = parse_coverage_xml(_COVERAGE_XML)
    assert isinstance(report, CoverageReport)
    # line-rate is a fraction 0..1; the parser surfaces percentages 0..100.
    assert report.total == 75.0
    assert report.per_file["pkg/a.py"] == 100.0
    assert report.per_file["pkg/b.py"] == 50.0


def test_coverage_total_falls_back_to_line_aggregate_when_attr_absent() -> None:
    """When the root has no ``line-rate`` attribute, the total is computed from
    aggregated per-file line hits."""
    xml = """\
<coverage>
  <packages><package><classes>
    <class filename="x.py">
      <lines><line number="1" hits="1"/><line number="2" hits="0"/></lines>
    </class>
  </classes></package></packages>
</coverage>
"""
    report = parse_coverage_xml(xml)
    assert report.per_file["x.py"] == 50.0
    assert report.total == 50.0


def test_coverage_empty_report_total_is_zero() -> None:
    report = parse_coverage_xml("<coverage></coverage>")
    assert report.per_file == {}
    assert report.total == 0.0


def test_coverage_class_without_filename_is_skipped() -> None:
    """A ``<class>`` with no ``filename`` attribute contributes nothing."""
    xml = (
        "<coverage><packages><package><classes>"
        '<class><lines><line number="1" hits="1"/></lines></class>'
        "</classes></package></packages></coverage>"
    )
    report = parse_coverage_xml(xml)
    assert report.per_file == {}


def test_coverage_file_without_lines_uses_line_rate_attr() -> None:
    """A file listing no ``<line>`` elements falls back to its ``line-rate``."""
    xml = (
        "<coverage><packages><package><classes>"
        '<class filename="x.py" line-rate="0.4"></class>'
        '<class filename="y.py"></class>'  # no line-rate either -> 0.0
        "</classes></package></packages></coverage>"
    )
    report = parse_coverage_xml(xml)
    assert report.per_file["x.py"] == 40.0
    assert report.per_file["y.py"] == 0.0


# --------------------------------------------------------------------------- #
# coverage: per-line hits, <sources> and repo-relative names (prK §F.1.1)
# --------------------------------------------------------------------------- #

_SOURCE_MODE_XML = """\
<?xml version="1.0" ?>
<coverage line-rate="0.6" version="7.0">
  <sources>
    <source>{source}</source>
  </sources>
  <packages>
    <package name="pkg" line-rate="0.6">
      <classes>
        <class filename="pkg/a.py" line-rate="0.6">
          <methods/>
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="3"/>
            <line number="4" hits="0"/>
            <line number="5" hits="1"/>
            <line number="7" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


def test_coverage_report_lines_and_sources_single_pass() -> None:
    report = parse_coverage_xml(_SOURCE_MODE_XML.format(source="/work/repo/src"))

    assert report.sources == ("/work/repo/src",)
    assert report.lines == {"pkg/a.py": {1: 1, 2: 3, 4: 0, 5: 1, 7: 0}}
    assert report.per_file["pkg/a.py"] == 60.0


def test_per_file_keys_unchanged() -> None:
    """``per_file`` keeps coverage.py's own ``filename``, so ``coverage`` scopes stay stable."""
    report = parse_coverage_xml(_COVERAGE_XML)

    assert set(report.per_file) == {"pkg/a.py", "pkg/b.py"}
    assert set(report.lines) == set(report.per_file)
    assert report.sources == ()


def test_coverage_lines_skip_rows_without_a_line_number() -> None:
    xml = (
        "<coverage><packages><package><classes>"
        '<class filename="x.py"><lines><line hits="1"/><line number="3" hits="2"/></lines>'
        "</class></classes></package></packages></coverage>"
    )

    report = parse_coverage_xml(xml)

    assert report.lines == {"x.py": {3: 2}}
    assert report.per_file["x.py"] == 100.0  # both rows still count, as before


def test_repo_relative_resolves_against_source_roots(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("y = 2\n", encoding="utf-8")
    src = str(tmp_path / "src")

    assert repo_relative("pkg/a.py", (src,), tmp_path) == "src/pkg/a.py"
    # Several sources: the one where the file exists wins.
    assert repo_relative("pkg/b.py", (src, str(tmp_path)), tmp_path) == "pkg/b.py"
    # No <sources>: the name is already relative to the root.
    assert repo_relative("pkg/b.py", (), tmp_path) == "pkg/b.py"
    # A relative source (``relative_files = true``) is relative to the root.
    assert repo_relative("pkg/a.py", ("src",), tmp_path) == "src/pkg/a.py"


def test_repo_relative_outside_the_root_is_none(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    assert repo_relative("lib.py", (str(tmp_path / "elsewhere"),), root) is None
    assert repo_relative("../escape.py", (), root) is None
