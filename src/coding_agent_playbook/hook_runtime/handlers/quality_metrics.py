"""clean-code-metrics-nonregression: the ``quality-metrics`` Stop stage (specs/prK-hook-pack.md §E.2).

The repo's own ``playbook metrics`` gate, static only, over the Python files
this work touched (the session ledger, ``git diff HEAD`` and untracked files,
minus the ``eval_fixture`` path class), with ``--baseline git:HEAD``:

- it calls ``evaluators.metrics_gate.run_metrics_gate`` in-process (imported
  only when the stage runs) with ``run_tests=False`` **always**: a repo's
  ``[metrics] run_tests = true`` must never run its suite from a hook (§B.4).
  The baseline blobs come through the hook's hardened ``SafeGit``;
- ``[metrics]`` is read live, like the pre-commit hook it mirrors;
- severity mirrors the repo's gate: fail-level findings block only when
  ``.pre-commit-config.yaml`` declares ``playbook-metrics`` or
  ``coding-agent-playbook-metrics`` (the rendered ``precommit`` snapshot or a
  live scan) **and** ``[metrics] fail_on_breach`` is true; otherwise each is a
  context line. A file that cannot be parsed or measured, a bad ``[metrics]``
  table or any gate error is a context line too, never a crash.

At most :data:`MAX_FILES` files are measured per Stop. The registered stop
handler runs the stage alone when the coordinator is not selected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.paths import fold_key
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult, StopPlan
from coding_agent_playbook.hook_runtime.stop.tools import edited_py

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.git import GitPort
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

    type Gate = Callable[[Any, Any], Any]  # (MetricsGateRequest, MetricsGateDeps) -> result

__all__ = [
    "CONFIG_SCHEMA",
    "MAX_FILES",
    "METRICS_HOOK_IDS",
    "STAGE_NAME",
    "QualityMetricsStage",
    "clean_code_metrics_nonregression",
    "quality_metrics_stage",
]

STAGE_NAME: Final = "quality-metrics"
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
}
#: The pre-commit ids that make a metrics regression fail the commit (§E.2).
METRICS_HOOK_IDS: Final = frozenset({"playbook-metrics", "coding-agent-playbook-metrics"})
MAX_FILES: Final = 50
_PRECOMMIT: Final = ".pre-commit-config.yaml"
_PRECOMMIT_MAX_BYTES: Final = 1024 * 1024
#: What a hostile source, a bad ``[metrics]`` table or a git failure can raise.
_MEASURE_ERRORS: Final = (SyntaxError, RecursionError, MemoryError, ValueError, OSError)


@dataclass(slots=True, kw_only=True)
class QualityMetricsStage:
    """The ``quality-metrics`` stage of one Stop; ``gate`` is the injection point for a spy.

    Example::

        >>> stage = quality_metrics_stage(stop_event, ctx)  # doctest: +SKIP
        >>> stage.run(plan, deadline).status
        'warn'
    """

    ctx: HandlerContext
    root: str
    gate: Gate | None = None
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "block"
    _targets: list[str] | None = field(default=None, repr=False)

    def applies(self, plan: StopPlan) -> bool:
        """Active only when ``.py`` files outside the eval fixtures were touched."""
        return bool(self.targets(plan))

    def targets(self, plan: StopPlan) -> list[str]:
        """The touched ``.py`` files, repo-relative and existing (memoized per Stop)."""
        if self._targets is None:
            self._targets = _touched(plan, self.ctx, self.root)
        return self._targets

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Measure the touched files against ``HEAD``; red, warn (context lines) or green."""
        targets = self.targets(plan)
        if not targets or plan.head_tree is None:  # an unborn branch has no baseline
            return StageResult(STAGE_NAME, "green")
        try:
            result = self._measure(targets[:MAX_FILES])
        except _MEASURE_ERRORS as exc:
            return _warn([f"metrics not measured ({type(exc).__name__})"])
        except Exception as exc:  # MetricsGateUsageError: a bad [metrics] table or git ref
            return _warn([f"metrics not measured: {clip(clean_text(str(exc)), 120)}"])
        lines = [_finding_line(f) for f in result.report.findings if f.level == "fail"]
        notes = [f"{quote_data(label)} not measured: {why}" for label, why in result.skipped]
        if len(targets) > MAX_FILES:
            notes.append(f"(+{len(targets) - MAX_FILES} touched files not measured)")
        if lines and result.config.fail_on_breach and _gated(self.ctx, self.root):
            return StageResult(STAGE_NAME, "red", lines=(*lines, *notes))
        return _warn([*lines, *notes]) if lines or notes else StageResult(STAGE_NAME, "green")

    def _measure(self, targets: Sequence[str]) -> Any:
        from coding_agent_playbook.evaluators import metrics_gate as gates  # the stage runs

        root = Path(self.root)
        request = gates.MetricsGateRequest(
            repo_root=root,
            config=gates.load_metrics_config(root),
            paths=tuple(os.path.join(self.root, rel) for rel in targets),
            baseline="git:HEAD",
            run_tests=False,  # never the suite from a hook, whatever [metrics] run_tests says
        )
        git = self.ctx.git
        deps = gates.MetricsGateDeps(git_factory=lambda _timeout: PortBaselineGit(git))
        if self.gate is not None:
            return self.gate(request, deps)
        return gates.run_metrics_gate(request, deps=deps)


class PortBaselineGit:
    """``evaluators.baseline_git.BaselineGit`` over the hook's hardened ``GitPort``.

    Only ``HEAD`` blobs are read (the stage never runs a suite, so no worktree).
    Example: ``PortBaselineGit(ctx.git).read_sources(root, "HEAD", ["src/a.py"])``.
    """

    def __init__(self, git: GitPort) -> None:
        self._git = git

    def is_commit(self, repo_root: Path, ref: str) -> bool:
        """Only ``HEAD`` on a born branch."""
        return ref == "HEAD" and self._git.head_tree() is not None

    def read_sources(self, repo_root: Path, ref: str, rel_paths: Sequence[str]) -> dict[str, bytes]:
        """Each path's ``HEAD`` blob; paths absent there are left out."""
        blobs = {rel: self._git.cat_head(rel) for rel in rel_paths}
        return {rel: blob for rel, blob in blobs.items() if blob is not None}

    def add_worktree(self, repo_root: Path, worktree: Path, ref: str) -> None:
        """Never needed: the hook never measures a suite baseline."""
        raise NotImplementedError("the quality-metrics stage never runs a suite")

    def remove_worktree(self, repo_root: Path, worktree: Path) -> None:
        """Nothing to remove."""


def quality_metrics_stage(ev: CanonicalEvent, ctx: HandlerContext) -> QualityMetricsStage | None:
    """The ``quality-metrics`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``quality_metrics_stage(stop_event, ctx).name == "quality-metrics"``.
    """
    return None if ev.repo is None else QualityMetricsStage(ctx=ctx, root=ev.repo.worktree_root)


@register_hook_handler(
    "clean_code_metrics_nonregression",
    events=["stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def clean_code_metrics_nonregression(
    ev: CanonicalEvent, ctx: HandlerContext
) -> HandlerResult | None:
    """Run the ``quality-metrics`` stage alone (no coordinator selected).

    Example: ``clean_code_metrics_nonregression(stop_after_cc_growth, ctx).decision``.
    """
    stage = quality_metrics_stage(ev, ctx)
    return None if stage is None else run_alone(stage, ev, ctx)


def _touched(plan: StopPlan, ctx: HandlerContext, root: str) -> list[str]:
    """Ledger ``.py`` edits, then ``git diff HEAD`` and untracked ``.py`` files, eval fixtures out."""
    found = dict.fromkeys(edited_py(plan.ledger))
    found.update(dict.fromkeys(line.path for line in ctx.git.diff_added()))
    found.update(dict.fromkeys(ctx.git.ls_untracked()))
    fixtures = ctx.cfg.path_classes.get("eval_fixture")
    return [
        rel
        for rel in found
        if rel.endswith(".py")
        and not (fixtures is not None and fixtures.matches(fold_key(rel, ctx.platform)))
        and os.path.isfile(os.path.join(root, rel))
    ]


def _gated(ctx: HandlerContext, root: str) -> bool:
    """The repo gates metrics in pre-commit: the rendered snapshot or a live scan says so."""
    table = ctx.cfg.tables.get("precommit")
    rendered = table.get("playbook_hook_ids") if isinstance(table, dict) else None
    if isinstance(rendered, list) and METRICS_HOOK_IDS.intersection(rendered):
        return True
    return bool(METRICS_HOOK_IDS.intersection(_live_precommit_ids(root)))


def _live_precommit_ids(root: str) -> Iterable[str]:
    from coding_agent_playbook.hook_runtime.handlers._control_plane_text import (
        playbook_precommit_ids,
    )

    try:
        with open(os.path.join(root, _PRECOMMIT), "rb") as handle:
            data = handle.read(_PRECOMMIT_MAX_BYTES)
    except OSError:
        return ()
    return playbook_precommit_ids(data.decode("utf-8", errors="replace"))


def _finding_line(finding: Any) -> str:
    """``"src/x.py"::parse cyclomatic_complexity 6 -> 9 (regression)``."""
    path, _, scope = str(finding.scope_key).partition("::")
    where = f"{quote_data(path)}::{clip(clean_text(scope), 60)}" if scope else quote_data(path)
    if finding.baseline is not None:
        change = f"{finding.baseline:g} -> {finding.value:g}"
    else:
        change = f"= {finding.value:g}"
    return f"{where} {finding.evaluator} {change} ({finding.kind})"


def _warn(lines: Sequence[str]) -> StageResult:
    return StageResult(STAGE_NAME, "warn", lines=tuple(lines))
