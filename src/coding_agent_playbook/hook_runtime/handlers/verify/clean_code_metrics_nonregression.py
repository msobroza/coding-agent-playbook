"""clean-code-metrics-nonregression: the ``quality-metrics`` Stop stage (specs/prK-hook-pack.md §E.2, §F.2.2).

The repo's own ``playbook metrics`` gate, static only, over the Python files
this work touched, with ``--baseline git:HEAD``: the ``quality`` family of the
consumer's ``[metrics]`` selection (``cognitive_complexity`` too when selected,
through the complexipy pin) plus ``ruff_violations``' ``ruff:quality`` counts
(C901, PLR0911, PLR0912, PLR0913, PLR0915). It reads the one pass it
shares with the ``docstrings`` stage (``_metrics_pass``), so nothing is
measured twice per Stop.

- **severity** mirrors the repo's gate: a fail-level finding blocks only when
  ``[metrics] fail_on_breach`` is true and the consumer's own selection
  includes the metric (so ``ruff_violations`` blocks only for a consumer who
  selected it), and, under the default ``[hooks.clean-code-metrics-nonregression]
  block = "auto"``, ``.pre-commit-config.yaml`` declares ``playbook-metrics`` or
  ``coding-agent-playbook-metrics``; ``block = "always"`` drops that last
  condition. Otherwise each is a context line. A file that cannot be measured,
  a bad ``[metrics]`` table or any gate error is a context line too, never a
  crash;
- each line ends with the fix note: the value that passes and how to get
  there (``passes at <= 5: split branches into helpers``);
- at most :data:`MAX_LINES` lines, then ``+N more (playbook metrics ...)``.

The **post-edit companion** (on by default; ``[hooks.clean-code-metrics-nonregression]
lint_feedback = false`` turns it off) is the ``quality`` bucket of the §E.3
shared D1 ruff call: no metric code, the family's codes and the
``[metrics.ruff_violations] config`` thresholds that sync renders into its
config. PLR1702 stays opt-in: it runs only under ``[metrics.ruff_violations]
preview = true``, in its own ``--preview`` call. The registered stop handler
runs the stage alone when the coordinator is not selected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers.verify._metrics_pass import (
    BLOCK_AUTO,
    BLOCK_KEY,
    MAX_FILES,
    METRICS_HOOK_IDS,
    PortBaselineGit,
    block_policy,
    capped,
    finding_line,
    ruff_detail,
    ruff_line,
    shared_pass,
    touched_py,
)
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult, StopPlan

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.grading.types import ScopeDetail
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers.verify._metrics_pass import MetricsPass

    type Gate = Callable[[Any, Any], Any]  # (MetricsGateRequest, MetricsGateDeps) -> result

__all__ = [
    "CONFIG_SCHEMA",
    "HOOK_ID",
    "MAX_FILES",
    "MAX_LINES",
    "METRICS_HOOK_IDS",
    "POST_EDIT_CONFIG_SCHEMA",
    "STAGE_NAME",
    "PortBaselineGit",
    "QualityMetricsStage",
    "clean_code_metrics_nonregression",
    "clean_code_metrics_post_edit",
    "quality_metrics_stage",
]

STAGE_NAME: Final = "quality-metrics"
#: The shipped hook whose ``[hooks.<id>] block`` this stage reads (``block_policy``).
HOOK_ID: Final = "clean-code-metrics-nonregression"
FAMILY: Final = "quality"
MAX_LINES: Final = 6
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "block": BLOCK_KEY,
}
#: ``lint_codes`` / ``ruff_config`` / ``ruff_preview`` are rendered at sync from
#: ``[metrics.ruff_violations]``, the one source shared with the Stop stage.
POST_EDIT_CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "lint_feedback": ConfigKey("boolean"),
}
_DECISIONS: Final = ["deny", "context", "none"]  # the hook's set (H5): stop denies, post-edit adds


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
    git_dir: str | None = None
    gate: Gate | None = None
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "block"
    block: str = BLOCK_AUTO
    _targets: list[str] | None = field(default=None, repr=False)

    def applies(self, plan: StopPlan) -> bool:
        """Active only when ``.py`` files outside the eval fixtures were touched."""
        return bool(self.targets(plan))

    def targets(self, plan: StopPlan) -> list[str]:
        """The touched ``.py`` files, repo-relative and existing (memoized per Stop)."""
        if self._targets is None:
            self._targets = touched_py(plan, self.ctx, self.root)
        return self._targets

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Measure the touched files against ``HEAD``; red, warn (context lines) or green."""
        targets = self.targets(plan)
        if not targets or plan.head_tree is None:  # an unborn branch has no baseline
            return StageResult(STAGE_NAME, "green")
        found = shared_pass(
            plan, self.ctx, self.root, deadline, git_dir=self.git_dir, gate=self.gate
        )
        if found.error:
            return _warn([found.error])
        mine = [f for f in found.fails() if _in_quality(f)]
        lines = capped([self._line(found, f) for f in mine], MAX_LINES)
        notes = _notes(found, len(targets))
        if any(found.deny_eligible(f.evaluator, self.block) for f in mine):
            return StageResult(STAGE_NAME, "red", lines=(*lines, *notes))
        return _warn([*lines, *notes]) if lines or notes else StageResult(STAGE_NAME, "green")

    def _line(self, found: MetricsPass, finding: ScopeDetail) -> str:
        note = found.fix_note(finding)
        if finding.evaluator != "ruff_violations":
            return finding_line(finding, note)
        rel = str(finding.scope_key).partition("::")[0]
        detail = ruff_detail(found, self.ctx, self.root, rel, FAMILY)
        return ruff_line(finding, FAMILY, detail, note)


def _in_quality(finding: ScopeDetail) -> bool:
    """A ``quality``-family finding: a quality metric, or ruff's ``ruff:quality`` count."""
    from coding_agent_playbook.grading.static_metrics.ruff_violations import ruff_family
    from coding_agent_playbook.metrics_gate.policy import METRIC_FAMILIES

    if finding.evaluator == "ruff_violations":
        return ruff_family(finding.scope_key) == FAMILY
    return finding.evaluator in METRIC_FAMILIES[FAMILY]


def _notes(found: MetricsPass, touched: int) -> list[str]:
    """Files not measured and why; the cap; a selected metric without its tool's pin."""
    skipped = [] if found.result is None else found.result.skipped
    notes = [f"{quote_data(label)} not measured: {why}" for label, why in skipped]
    if touched > MAX_FILES:
        notes.append(f"(+{touched - MAX_FILES} touched files not measured)")
    notes.extend(found.tools_missing)
    return notes


def quality_metrics_stage(ev: CanonicalEvent, ctx: HandlerContext) -> QualityMetricsStage | None:
    """The ``quality-metrics`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``quality_metrics_stage(stop_event, ctx).name == "quality-metrics"``.
    """
    if ev.repo is None:
        return None
    return QualityMetricsStage(
        ctx=ctx,
        root=ev.repo.worktree_root,
        git_dir=ev.repo.git_dir,
        block=block_policy(ctx, HOOK_ID),
    )


@register_hook_handler(
    "clean_code_metrics_nonregression",
    events=["stop"],
    decisions=_DECISIONS,
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


@register_hook_handler(
    "clean_code_metrics_nonregression:post_edit",
    events=["post_tool_use"],
    decisions=_DECISIONS,
    config_schema=POST_EDIT_CONFIG_SCHEMA,
)
def clean_code_metrics_post_edit(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """The ``quality`` bucket of the shared D1 ruff call, on the lines an edit changed.

    Example::

        >>> clean_code_metrics_post_edit(edit_growing_parse, ctx).context  # doctest: +SKIP
        ('quality: "src/x.py:3 C901 `parse` is too complex (12 > 10)"',)
    """
    if not HookConfig(ctx.config, POST_EDIT_CONFIG_SCHEMA).flag("lint_feedback", True):
        return None  # switched off: it adds no code to D1 and spawns nothing
    from coding_agent_playbook.hook_runtime.handlers.feedback.ruff_feedback import bucket_feedback

    return bucket_feedback(ev, ctx, rule_id=FAMILY)


def _warn(lines: Sequence[str]) -> StageResult:
    return StageResult(STAGE_NAME, "warn", lines=tuple(lines))
