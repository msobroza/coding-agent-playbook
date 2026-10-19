"""coverage-diff-gate: the ``coverage`` Stop stage, changed-line coverage of the shared suite run (specs/prK-hook-pack.md §F.1.2).

Opt-in and trust-gated: an execution stage, so the coordinator runs it only
when no deterministic stage is red and the user approved this exact stage list
(§B.4); its hook applies only with ``has_dev_dependency: [pytest-cov]``. It
applies when the last message claims completion and Python lines changed
since the diff base (``HEAD``; ``diff_base = "merge-base"``: the merge base
with the default branch), test code and ``[metrics] exclude`` left out.

It reads the one suite run it shares with the ``tests`` stage
(``stop.suite``) and grades it with ``run_metrics_gate``, reading ``[metrics]``
live like its twins (OQ-40): ``diff_coverage`` (``fail`` below 80% by
default) and, only when ``<state>/coverage/<HEAD^{tree}>.json`` holds the
snapshot of a green run, total ``coverage`` non-regression against it; without
one the total is left to CI and says so. A green run writes the snapshot for
its own tree, so the commit of that tree has a baseline.

A red suite is never graded: the ``tests`` stage owns it when enabled, else
one ``suite red`` line. A timeout, a crash or a missing pytest-cov is
``NOT verified`` with one line for the user, never green. At most four lines;
``decision = "context"`` makes the stage advisory (``warn``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.handlers._coverage_report import (
    CoverageGrade,
    coverage_lines,
    head_snapshot,
    port_changed_lines,
    suite_total,
    write_snapshot_rows,
)
from coding_agent_playbook.hook_runtime.handlers._verify_claim import completion_claim
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evaluators.execution.project import ProjectHandle, RunArtifacts
    from coding_agent_playbook.hook_runtime.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.stages import SkipCategory, StopPlan
    from coding_agent_playbook.hook_runtime.stop.suite import SuiteOutcome
    from coding_agent_playbook.metrics_gate.run import MetricsGateResult
    from coding_agent_playbook.metrics_gate.suite import ProjectFactory

__all__ = [
    "CONFIG_SCHEMA",
    "STAGE_NAME",
    "CoverageStage",
    "coverage_diff_gate",
    "coverage_stage",
]

STAGE_NAME: Final = "coverage"
#: The MODULE label the gate keys the suite total on (``metrics_gate.suite``).
_SUITE_LABEL: Final = "suite"
_SELECT: Final = ("diff_coverage", "coverage")
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "timeout_s": ConfigKey("number"),
    "diff_base": ConfigKey("string", "replace", ("HEAD", "merge-base")),
    "decision": ConfigKey("string", "replace", ("deny", "context")),
}


@dataclass(slots=True, kw_only=True)
class CoverageStage:
    """The ``coverage`` stage of one Stop (module docstring).

    Example::

        >>> coverage_stage(stop_event, ctx).run(plan, deadline).lines[0]  # doctest: +SKIP
        'coverage: 62.5% of 24 changed lines executed (min 80%)'
    """

    ctx: HandlerContext
    repo: RepoInfo
    name: str = STAGE_NAME
    cost: StageCost = StageCost.EXECUTION
    needs_diff: bool = True
    mode: str = "block"
    _base: str | None = field(default=None, repr=False)
    _changes: dict[str, frozenset[int]] | None = field(default=None, repr=False)

    def applies(self, plan: StopPlan) -> bool:
        """Completion is claimed and scored (non-test, non-excluded) Python lines changed."""
        if completion_claim(plan.event, self.ctx.cfg) is None:
            return False
        return bool(self._scored())

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Grade the shared run: red/warn with at most four lines, green, or skipped."""
        from coding_agent_playbook.hook_runtime.stop.suite import shared_suite

        outcome = shared_suite(plan, self.ctx, self.repo).outcome(deadline)
        if outcome.problem is not None:
            notes = (outcome.problem.advice,) if outcome.problem.advice else ()
            return _skipped(outcome.problem.category, notes)
        artifacts = outcome.artifacts
        if outcome.red or artifacts is None or outcome.handle is None:
            return self._red_suite(outcome)
        try:
            grade = self._grade(plan, outcome.handle, artifacts)
        except Exception as exc:  # a bad [metrics] table (MetricsGateUsageError): never green
            return _skipped("crash", (f"coverage not graded: {clip(clean_text(str(exc)), 120)}",))
        lines = coverage_lines(grade)
        if not lines:
            fingerprint = plan.fingerprint
            if fingerprint is not None and not fingerprint.aux and fingerprint.tree_id:
                write_snapshot_rows(self.ctx.session.store, fingerprint.tree_id, grade.rows)
            return StageResult(STAGE_NAME, "green")
        return StageResult(
            STAGE_NAME, "red" if self.mode == "block" else "warn", lines=tuple(lines)
        )

    def _red_suite(self, outcome: SuiteOutcome) -> StageResult:
        """Not graded on a red suite; the ``tests`` stage reports it when enabled."""
        from coding_agent_playbook.hook_runtime.stop.tools import stage_command

        if stage_command(self.ctx.cfg, "tests") is not None:
            return _skipped("suite_red", ())
        junit = None if outcome.artifacts is None else outcome.artifacts.junit
        failed = 0 if junit is None else junit.failed + junit.errors
        return _skipped("suite_red", (f"suite red ({failed} failed); coverage not graded",))

    def _grade(
        self, plan: StopPlan, handle: ProjectHandle, artifacts: RunArtifacts
    ) -> CoverageGrade:
        from coding_agent_playbook.evaluators.execution.diff_coverage import (
            changed_line_coverage,
        )

        root = Path(self.repo.worktree_root)
        snapshot = head_snapshot(self.ctx.session.store, plan.head_tree)
        result = self._gate(root, handle, snapshot)
        findings = result.report.findings
        detail = changed_line_coverage(
            self._changes or {}, artifacts.coverage, root=root, exclude=result.config.exclude
        )
        return CoverageGrade(
            detail=detail,
            diff=next((f for f in findings if f.evaluator == "diff_coverage"), None),
            total=suite_total(findings, _SUITE_LABEL),
            compared=snapshot is not None,
            rows=tuple(f for f in findings if f.evaluator == "coverage"),
        )

    def _gate(self, root: Path, handle: ProjectHandle, snapshot: Path | None) -> MetricsGateResult:
        """``run_metrics_gate`` over the shared run: no new suite run, ``[metrics]`` read live."""
        from coding_agent_playbook.hook_runtime.handlers._metrics_pass import PortBaselineGit
        from coding_agent_playbook.metrics_gate import run as gates

        config = gates.load_metrics_config(root)
        changes = self._changes or {}
        targets = tuple(str(root / rel) for rel in self._scored() if (root / rel).is_file())
        request = gates.MetricsGateRequest(
            repo_root=root,
            config=config,
            paths=targets,
            baseline=None if snapshot is None else f"json:{snapshot}",
            run_tests=True,  # the run already happened: the handle replays it
            select=_SELECT,
            extend_select=(),
            diff_base=self._diff_base(),
        )
        git = self.ctx.git
        deps = gates.MetricsGateDeps(
            project_factory=_replay(handle),
            load_static_metrics=list,
            git_factory=lambda _timeout_s: PortBaselineGit(git),
            changed_lines=lambda _root, _base: changes,
        )
        return gates.run_metrics_gate(request, deps=deps)

    def _diff_base(self) -> str:
        """``HEAD``, or the merge base with the default branch (``HEAD`` when there is none)."""
        if self._base is None:
            self._base = "HEAD"
            if self.ctx.config.get("diff_base") == "merge-base":
                branch = self.ctx.git.default_branch()
                merged = None if branch is None else self.ctx.git.merge_base(branch, "HEAD")
                self._base = merged or "HEAD"
        return self._base

    def _scored(self) -> list[str]:
        """The changed paths the gate scores (memoized per Stop); none on a git error."""
        from coding_agent_playbook.evaluators.execution.diff_coverage import scored_changes
        from coding_agent_playbook.hook_runtime.git.safe_git import GitError

        if self._changes is None:
            root = Path(self.repo.worktree_root)
            try:
                self._changes = port_changed_lines(self.ctx.git, root, self._diff_base())
            except GitError:  # an unborn branch or an unreadable diff: nothing to grade
                self._changes = {}
        exclude = _exclude(self.ctx, self.repo)
        return sorted(scored_changes(self._changes, exclude=exclude))


def _replay(handle: ProjectHandle) -> ProjectFactory:
    """A ``ProjectFactory`` handing back the shared run's handle with the gate's diff base."""

    def factory(
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        *,
        diff_base: str | None = None,
        timeout_s: float | None = None,
        cov_sources: Sequence[str] = (),
    ) -> ProjectHandle:
        handle.diff_base = diff_base
        return handle

    return factory


def _exclude(ctx: HandlerContext, repo: RepoInfo) -> tuple[str, ...]:
    """``[metrics] exclude`` (read live, memoized per event); the engine default on a bad table."""
    from coding_agent_playbook.metrics_gate import run as gates
    from coding_agent_playbook.metrics_gate.config import MetricConfig

    def read() -> tuple[str, ...]:
        try:
            return gates.load_metrics_config(Path(repo.worktree_root)).exclude
        except gates.MetricsGateUsageError:
            return MetricConfig().exclude

    found: tuple[str, ...] = ctx.memo.get_or_compute(("metrics-exclude", repo.worktree_root), read)
    return found


def _skipped(category: SkipCategory, notes: tuple[str, ...]) -> StageResult:
    return StageResult(STAGE_NAME, "skipped", user_lines=notes, skip_category=category)


def coverage_stage(ev: CanonicalEvent, ctx: HandlerContext) -> CoverageStage | None:
    """The ``coverage`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``coverage_stage(stop_event, ctx).cost is StageCost.EXECUTION``.
    """
    if ev.repo is None:
        return None
    mode = "warn" if ctx.config.get("decision") == "context" else "block"
    return CoverageStage(ctx=ctx, repo=ev.repo, mode=mode)


@register_hook_handler(
    "coverage_diff_gate",
    events=["stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def coverage_diff_gate(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``coverage`` stage alone (no coordinator), only with the user's execution approval.

    Example: ``coverage_diff_gate(stop_claiming_done, ctx)`` is ``None`` in an untrusted repo.
    """
    stage = coverage_stage(ev, ctx)
    if stage is None or ev.repo is None or not _trusted(ev.repo, ctx):
        return None
    return run_alone(stage, ev, ctx)


def _trusted(repo: RepoInfo, ctx: HandlerContext) -> bool:
    """The user approved this repo's rendered Stop stage list on this machine (§B.4)."""
    from coding_agent_playbook.hook_runtime._ports import open_trust_store
    from coding_agent_playbook.hook_runtime.stop.coordinator import GatePolicy

    trust = None if ctx.deps is None else open_trust_store(repo, ctx.deps)
    policy = GatePolicy.from_gate(ctx.cfg.tables.stop_gate())
    return trust is not None and trust.allows_execution(policy.stages_sha256())
