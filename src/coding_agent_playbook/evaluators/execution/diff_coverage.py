"""``diff_coverage`` — the share of the changed executable lines the suite ran (prK §F.1.1).

It is the attribution-correct coverage signal: it scores exactly the lines a
change added or edited, so it needs **one** suite run and no baseline run
(``diff_based = True``). The changed lines come from
:func:`~coding_agent_playbook.evaluators.execution.git_diff.changed_lines`
against ``ProjectHandle.diff_base``; the executable lines and their hits come
from the same cached :meth:`ProjectHandle.run` the ``coverage`` metric reads.

Test code is never scored (``TEST_PATH_GLOBS``: it is executed by definition,
so it would inflate the score whenever tests are added), and neither is a path
matching ``[metrics] exclude``. A changed file the coverage report does not list
is **unmeasured**: named in :class:`DiffCoverage`, not scored. With no changed
executable line the metric yields nothing, so its check passes vacuously and
never on a fake 100%.

:func:`changed_line_coverage` is the pure core, shared by the metric, the CLI
and the ``coverage-diff-gate`` hook message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evaluators.execution.coverage_xml import repo_relative
from coding_agent_playbook.evaluators.execution.git_diff import changed_lines
from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.normalizer import PercentNormalizer
from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.paths import is_test_path, matches_any_glob
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.evaluators.execution.coverage_xml import CoverageReport
    from coding_agent_playbook.evaluators.types import EvalContext

__all__ = [
    "DIFF_COVERAGE",
    "DiffCoverage",
    "DiffCoverageMetric",
    "FileDiffCoverage",
    "changed_line_coverage",
    "format_ranges",
    "line_ranges",
    "scored_changes",
]

#: The metric name; the metrics gate keys source-mode ``--cov`` on it.
DIFF_COVERAGE: Final = "diff_coverage"


@dataclass(frozen=True)
class FileDiffCoverage:
    """One scored file: its changed executable lines, how many ran, and the missed runs.

    Example::

        >>> FileDiffCoverage("src/a.py", executable=4, covered=3, uncovered=((7, 7),)).percent
        75.0
    """

    path: str
    executable: int
    covered: int
    uncovered: tuple[tuple[int, int], ...]

    @property
    def percent(self) -> float:
        """Covered over executable, as a percentage (``executable`` is never 0 here)."""
        return 100.0 * self.covered / self.executable


@dataclass(frozen=True)
class DiffCoverage:
    """Changed-line coverage of one run: the scored files plus the unmeasured ones.

    Example::

        >>> DiffCoverage().percent is None
        True
    """

    files: tuple[FileDiffCoverage, ...] = ()
    unmeasured: tuple[str, ...] = ()

    @property
    def executable(self) -> int:
        """Changed executable lines over every scored file."""
        return sum(item.executable for item in self.files)

    @property
    def covered(self) -> int:
        """How many of them the suite ran."""
        return sum(item.covered for item in self.files)

    @property
    def percent(self) -> float | None:
        """``100 · covered / executable``; ``None`` when no changed line is executable."""
        return None if self.executable == 0 else 100.0 * self.covered / self.executable


def scored_changes(
    changed: Mapping[str, frozenset[int]], *, exclude: Sequence[str] = ()
) -> dict[str, frozenset[int]]:
    """``changed`` without test code (``TEST_PATH_GLOBS``) and paths matching ``exclude``.

    Example::

        >>> scored_changes({"tests/test_a.py": frozenset({1}), "src/a.py": frozenset({2})})
        {'src/a.py': frozenset({2})}
    """
    return {
        path: lines
        for path, lines in changed.items()
        if not is_test_path(path) and not matches_any_glob(path, exclude)
    }


def changed_line_coverage(
    changed: Mapping[str, frozenset[int]],
    report: CoverageReport,
    *,
    root: Path,
    exclude: Sequence[str] = (),
) -> DiffCoverage:
    """Score the changed lines of ``changed`` (root-relative paths) against ``report``.

    A file's executable changed lines are ``changed ∩ report.lines``; a line
    with ``hits > 0`` is covered. Files are listed in path order; a changed file
    the report does not name is unmeasured; one with no executable changed line
    is left out.

    Example::

        >>> report = CoverageReport(lines={"a.py": {1: 1, 2: 0, 3: 0}})
        >>> changed_line_coverage({"a.py": frozenset({2, 3, 9})}, report, root=Path(".")).percent
        0.0
    """
    measured = _measured_lines(report, root)
    files: list[FileDiffCoverage] = []
    unmeasured: list[str] = []
    for path, lines in sorted(scored_changes(changed, exclude=exclude).items()):
        hits = measured.get(path)
        if hits is None:
            unmeasured.append(path)
            continue
        executable = lines & hits.keys()
        if executable:
            missed = [line for line in sorted(executable) if hits[line] == 0]
            covered = len(executable) - len(missed)
            files.append(FileDiffCoverage(path, len(executable), covered, line_ranges(missed)))
    return DiffCoverage(tuple(files), tuple(unmeasured))


def line_ranges(lines: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """Line numbers collapsed into sorted, inclusive ``(first, last)`` runs.

    Example::

        >>> line_ranges([15, 12, 13, 14, 40])
        ((12, 15), (40, 40))
    """
    runs: list[tuple[int, int]] = []
    for line in sorted(set(lines)):
        if runs and runs[-1][1] == line - 1:
            runs[-1] = (runs[-1][0], line)
        else:
            runs.append((line, line))
    return tuple(runs)


def format_ranges(ranges: Iterable[tuple[int, int]]) -> str:
    """``((12, 15), (40, 40))`` as ``"12-15, 40"``, the form the hook and CLI print.

    Example::

        >>> format_ranges(((12, 15), (40, 40)))
        '12-15, 40'
    """
    return ", ".join(str(first) if first == last else f"{first}-{last}" for first, last in ranges)


def _measured_lines(report: CoverageReport, root: Path) -> dict[str, dict[int, int]]:
    """``report.lines`` keyed by root-relative path; names outside ``root`` are dropped."""
    measured: dict[str, dict[int, int]] = {}
    for filename, hits in report.lines.items():
        rel = repo_relative(filename, report.sources, root)
        if rel is not None:
            measured[rel] = hits
    return measured


def _measure(ctx: EvalContext) -> list[Measurement]:
    """One MODULE measurement (key ``ctx.label``): the changed-line coverage percentage.

    Nothing without a project or a diff base (a baseline handle has none), and
    nothing, without running the suite, when no scored file changed.
    """
    project = ctx.project
    base = getattr(project, "diff_base", None)
    if project is None or base is None:
        return []
    setup = ctx.tool_setup
    git = None if setup.git is None else setup.git(project.root, setup.timeout_s)
    found = changed_lines(project.root, base, timeout_s=setup.timeout_s, git=git)
    changed = scored_changes(found, exclude=setup.exclude)
    if not changed:
        return []
    result = changed_line_coverage(changed, project.run().coverage, root=project.root)
    if result.percent is None:
        return []
    return [Measurement(DIFF_COVERAGE, scope_key(ctx.label, None), result.percent)]


@register_metric
class DiffCoverageMetric(Metric):
    """``diff_coverage`` as a :class:`Metric`: a MODULE percentage over the changed lines.

    ``needs_project=True`` (an execution metric) and ``diff_based=True`` (no
    baseline run).

    Example::

        >>> DiffCoverageMetric().measure(EvalContext(module=None, source="", label="suite"))
        []
    """

    name = DIFF_COVERAGE
    scope = Scope.MODULE
    normalizer = PercentNormalizer()
    requires = None
    needs_project = True
    diff_based = True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        """See :func:`_measure`."""
        return _measure(ctx)
