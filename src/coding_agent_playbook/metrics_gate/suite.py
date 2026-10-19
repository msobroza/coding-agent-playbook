"""Suite runs for the metrics gate's execution metrics (``run_tests``; PR-M M4, prK §F.0.3).

One :class:`SuiteRun` runs the project's suite once per root and measures
``test_pass_rate`` / ``coverage`` / ``diff_coverage`` from it;
:func:`suite_baseline` runs it again on a ``git:`` ref (through a temporary
worktree) or a baseline directory. Only the candidate run gets a diff base, so a
diff-based metric measures nothing on the baseline. Import the public names
from ``metrics_gate``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from coding_agent_playbook.evaluators.baseline_git import BaselineGitError
from coding_agent_playbook.evaluators.execution.diff_coverage import DIFF_COVERAGE
from coding_agent_playbook.evaluators.execution.project import import_roots
from coding_agent_playbook.evaluators.types import EvalContext, ToolSetup
from coding_agent_playbook.metrics_gate.inputs import (
    GIT_PREFIX,
    JSON_PREFIX,
    MetricsGateUsageError,
    git_usage_error,
    verify_git_ref,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evaluators.baseline_git import BaselineGit
    from coding_agent_playbook.evaluators.execution.project import ProjectHandle
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.types import Measurement
    from coding_agent_playbook.metrics_gate.run import MetricsGateRequest

#: MODULE label the execution metrics key their suite-wide measurements on.
SUITE_LABEL = "suite"


class ProjectFactory(Protocol):
    """Builds the :class:`ProjectHandle` a suite run measures (``ProjectHandle.create``).

    ``diff_base`` is set on the candidate handle only; ``timeout_s`` bounds the
    run; ``cov_sources`` shape the default command (never an explicit one).
    """

    def __call__(
        self,
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        *,
        diff_base: str | None = None,
        timeout_s: float | None = None,
        cov_sources: Sequence[str] = (),
    ) -> ProjectHandle: ...


@dataclass(frozen=True)
class SuiteRun:
    """Runs the execution metrics over one project root: one suite run per root.

    ``test_cmd`` is exactly what runs (``None`` = the handle's isolated pytest
    default); it is never read from ``[metrics] test_cmd``. ``timeout_s`` bounds
    each run (``[metrics] test_timeout_s``). ``source_mode`` puts the default
    command's coverage in source mode (``--cov=<import root>``), so a
    never-imported file counts as uncovered for ``diff_coverage``.
    ``tool_setup`` is how a diff-based metric reads git, and ``diff_base`` the
    ref it diffs the candidate against (:func:`run_suites` gives it to the
    candidate run only).
    """

    metrics: Sequence[Metric]
    test_cmd: list[str] | None
    project_factory: ProjectFactory
    tool_paths: Mapping[str, str]
    timeout_s: float | None = None
    source_mode: bool = False
    tool_setup: ToolSetup = field(default_factory=ToolSetup)
    diff_base: str | None = None

    def measure(
        self, root: Path, report_dir: Path, *, diff_base: str | None = None
    ) -> list[Measurement]:
        """Build a handle, run the suite once, and collect execution measurements.

        Every execution metric reads the same handle, so the suite runs exactly
        once. Raises :class:`MetricsGateUsageError` when the suite cannot be run
        (or times out), or when a diff-based metric cannot read git.
        """
        handle = self.project_factory(
            root,
            report_dir,
            test_cmd=self.test_cmd,
            diff_base=diff_base,
            timeout_s=self.timeout_s,
            cov_sources=import_roots(root) if self.source_mode and self.test_cmd is None else (),
        )
        ctx = EvalContext(
            module=None,
            source="",
            label=SUITE_LABEL,
            project=handle,
            tool_paths=self.tool_paths,
            tool_setup=self.tool_setup,
        )
        measurements: list[Measurement] = []
        try:
            for metric in self.metrics:
                if metric.available(ctx):
                    measurements.extend(metric.measure(ctx))
        except RuntimeError as exc:
            raise MetricsGateUsageError(str(exc)) from exc
        return measurements

    @property
    def diff_based_only(self) -> bool:
        """Every metric measures relative to a diff base, so a baseline run is meaningless."""
        return all(metric.diff_based for metric in self.metrics)


def gate_suite(
    request: MetricsGateRequest,
    execution: Sequence[Metric],
    factory: ProjectFactory,
    setup: ToolSetup,
) -> SuiteRun:
    """The suite run of one gate request: its command, bound, diff base and coverage mode.

    ``diff_coverage`` puts the default command in coverage source mode only
    when it will measure (a diff base exists), so a run without one keeps
    today's command.

    Example::

        >>> gate_suite(request, execution_metrics(), ProjectHandle.create, setup).diff_base
        'HEAD'
    """
    diff_base = diff_base_for(request.baseline, request.diff_base)
    measures_diff = any(metric.name == DIFF_COVERAGE for metric in execution)
    return SuiteRun(
        execution,
        None if request.test_cmd is None else list(request.test_cmd),
        factory,
        request.tool_paths,
        timeout_s=request.config.test_timeout_s,
        source_mode=diff_base is not None and measures_diff,
        tool_setup=setup,
        diff_base=diff_base,
    )


def diff_base_for(baseline: str | None, explicit: str | None) -> str | None:
    """The ref diff-based metrics diff against: ``explicit``, else a ``git:`` baseline's ref.

    Example::

        >>> diff_base_for("git:origin/main", None), diff_base_for("json:cov.json", None)
        ('origin/main', None)
    """
    if explicit is not None:
        return explicit
    if baseline is not None and baseline.startswith(GIT_PREFIX):
        return baseline[len(GIT_PREFIX) :]
    return None


def without_diff_based(
    baseline: list[Measurement] | None, execution: Sequence[Metric]
) -> list[Measurement] | None:
    """``baseline`` minus the diff-based metrics' rows, which a ``json:`` snapshot carries.

    A diff-based value is relative to its own diff base, so comparing two of
    them is meaningless; without a baseline row the candidate grades as new.

    Example::

        >>> without_diff_based([Measurement("diff_coverage", "suite", 90.0)], [DiffCoverageMetric()])
        []
    """
    names = {metric.name for metric in execution if metric.diff_based}
    if baseline is None or not names:
        return baseline
    return [row for row in baseline if row.evaluator not in names]


def run_suites(
    suite: SuiteRun, repo_root: Path, baseline: str | None, *, git: BaselineGit
) -> tuple[list[Measurement], list[Measurement]]:
    """``(candidate, baseline)`` execution measurements: the candidate run, then the baseline's.

    Only the candidate run gets ``suite.diff_base``. The baseline suite runs
    only for a ``git:`` or directory baseline: a ``json:`` snapshot already
    carries its execution measurements, and when every metric is diff-based
    there is nothing to compare, so ``--select diff_coverage`` costs one suite
    run, not two.

    Example::

        >>> run_suites(suite, Path("."), "git:HEAD", git=git)  # doctest: +SKIP
        ([Measurement(evaluator='diff_coverage', scope_key='suite', value=62.5)], [])
    """
    with tempfile.TemporaryDirectory(prefix="playbook-metrics-") as tmp:
        work_dir = Path(tmp)
        reports = work_dir / "candidate-reports"
        candidate = suite.measure(repo_root, reports, diff_base=suite.diff_base)
        if baseline is None or baseline.startswith(JSON_PREFIX) or suite.diff_based_only:
            return candidate, []
        return candidate, suite_baseline(baseline, repo_root, suite, work_dir, git)


def suite_baseline(
    baseline: str, repo_root: Path, suite: SuiteRun, work_dir: Path, git: BaselineGit
) -> list[Measurement]:
    """Run the execution metrics on the baseline (a git ref or a directory).

    ``git:<ref>`` materialises the ref via a temporary worktree under
    ``work_dir`` (removed afterwards); ``<dir>`` runs the suite directly in that
    directory. Raises :class:`MetricsGateUsageError` on a bad ref, a non-git dir,
    a missing directory, a git timeout or an unrunnable suite.
    """
    if baseline.startswith(GIT_PREFIX):
        ref = baseline[len(GIT_PREFIX) :]
        verify_git_ref(git, repo_root, ref)
        return _suite_in_worktree(ref, repo_root, suite, work_dir, git)
    base_dir = Path(baseline)
    if not base_dir.is_dir():
        raise MetricsGateUsageError(f"baseline directory not found: {base_dir}")
    return suite.measure(base_dir, work_dir / "baseline-reports")


def _suite_in_worktree(
    ref: str, repo_root: Path, suite: SuiteRun, work_dir: Path, git: BaselineGit
) -> list[Measurement]:
    """Materialise ``ref`` in a temp git worktree, run the suite, then clean up."""
    worktree = work_dir / "baseline-worktree"
    try:
        git.add_worktree(repo_root, worktree, ref)
    except BaselineGitError as exc:
        raise git_usage_error(exc, f"could not create baseline worktree for {ref!r}") from exc
    try:
        return suite.measure(worktree, work_dir / "baseline-reports")
    finally:
        git.remove_worktree(repo_root, worktree)
