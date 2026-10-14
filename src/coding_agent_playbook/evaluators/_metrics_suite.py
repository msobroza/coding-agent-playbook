"""Suite runs for the metrics gate's execution metrics (``run_tests``; PR-M M4, prK §F.0.3).

One :class:`SuiteRun` runs the project's suite once per root and measures
``test_pass_rate`` / ``coverage`` from it; :func:`suite_baseline` runs it again on
a ``git:`` ref (through a temporary worktree) or a baseline directory. Import the
public names from ``metrics_gate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from coding_agent_playbook.evaluators._metrics_inputs import (
    GIT_PREFIX,
    MetricsGateUsageError,
    git_usage_error,
    verify_git_ref,
)
from coding_agent_playbook.evaluators.baseline_git import BaselineGitError
from coding_agent_playbook.evaluators.types import EvalContext

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evaluators.baseline_git import BaselineGit
    from coding_agent_playbook.evaluators.execution.project import ProjectHandle
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.types import Measurement

#: MODULE label the execution metrics key their suite-wide measurements on.
SUITE_LABEL = "suite"


class ProjectFactory(Protocol):
    """Builds the :class:`ProjectHandle` a suite run measures (``ProjectHandle.create``)."""

    def __call__(
        self, root: Path, report_dir: Path, test_cmd: list[str] | None = None
    ) -> ProjectHandle: ...


@dataclass(frozen=True)
class SuiteRun:
    """Runs the execution metrics over one project root: one suite run per root.

    ``test_cmd`` is exactly what runs (``None`` = the handle's isolated pytest
    default); it is never read from ``[metrics] test_cmd``.
    """

    metrics: Sequence[Metric]
    test_cmd: list[str] | None
    project_factory: ProjectFactory
    tool_paths: Mapping[str, str]

    def measure(self, root: Path, report_dir: Path) -> list[Measurement]:
        """Build a handle, run the suite once, and collect execution measurements.

        Every execution metric reads the same handle, so the suite runs exactly
        once. Raises :class:`MetricsGateUsageError` when the suite cannot be run.
        """
        handle = self.project_factory(root, report_dir, test_cmd=self.test_cmd)
        ctx = EvalContext(
            module=None, source="", label=SUITE_LABEL, project=handle, tool_paths=self.tool_paths
        )
        measurements: list[Measurement] = []
        try:
            for metric in self.metrics:
                if metric.available(ctx):
                    measurements.extend(metric.measure(ctx))
        except RuntimeError as exc:
            raise MetricsGateUsageError(str(exc)) from exc
        return measurements


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
