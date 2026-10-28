"""docstring-nonregression: the ``docstrings`` Stop stage and its post-edit bucket (specs/prK-hook-pack.md §F.3.2).

**Stop** (stage 3, deterministic): the ``ruff:docstrings`` counts (D100-D107)
of the metrics pass this stage shares with ``quality-metrics``
(``_metrics_pass``): removing a docstring, or adding an undocumented public
symbol to a touched file, raises the file's count over ``HEAD``; legacy
undocumented code stays silent (the count is unchanged). With the opt-in
``docstring_example`` selected, a public function whose docstring lacks a
usage example is named too. Test modules and eval fixtures are never in scope.
Severity is the shared rule: deny-eligible only with ``fail_on_breach`` **and**
the metric in the consumer's own selection, and, under the default
``[hooks.docstring-nonregression] block = "auto"``, a playbook metrics hook in
pre-commit (``block = "always"`` drops that condition); else a context line.
At most :data:`MAX_LINES` lines, then ``+N more``.

**Post-edit** adds no logic: through the linked ``python-docstrings`` rule's
``lint_codes`` it contributes D100-D107 to the single §E.3 D1 ruff call, on the
changed lines only (a def counts only when new or its signature line changed).
``[hooks.docstring-nonregression] lint_feedback = false`` drops the codes from D1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers.verify._metrics_pass import (
    BLOCK_AUTO,
    BLOCK_KEY,
    block_policy,
    capped,
    is_test_path,
    ruff_detail,
    ruff_line,
    shared_pass,
    touched_py,
)
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult, StopPlan

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.grading.types import ScopeDetail
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers.verify._metrics_pass import MetricsPass

    type Gate = Callable[[Any, Any], Any]  # (MetricsGateRequest, MetricsGateDeps) -> result

__all__ = [
    "CONFIG_SCHEMA",
    "HOOK_ID",
    "MAX_LINES",
    "POST_EDIT_CONFIG_SCHEMA",
    "STAGE_NAME",
    "STRICT_HINT",
    "DocstringsStage",
    "docstring_nonregression",
    "docstring_nonregression_post_edit",
    "docstrings_stage",
]

STAGE_NAME: Final = "docstrings"
FAMILY: Final = "docstrings"
MAX_LINES: Final = 5
#: What strict mode (``docstring_example``) asks of a public function (§F.3.1).
STRICT_HINT: Final = "needs an intent line + one usage example (>>>, Example:, or Usage::)"
#: The shipped hook whose ``[hooks.<id>] block`` this stage reads (``block_policy``).
HOOK_ID: Final = "docstring-nonregression"
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "block": BLOCK_KEY,
}
#: ``lint_codes`` comes from the linked ``python-docstrings`` rule (resolved at sync).
POST_EDIT_CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "lint_feedback": ConfigKey("boolean"),
}
_RULE: Final = "python-docstrings"
_DECISIONS: Final = ["deny", "context", "none"]  # the hook's set (H5): stop denies, post-edit adds


@dataclass(slots=True, kw_only=True)
class DocstringsStage:
    """The ``docstrings`` stage of one Stop; ``gate`` is the injection point for a spy.

    Example::

        >>> docstrings_stage(stop_event, ctx).run(plan, deadline).lines  # doctest: +SKIP
        ('"src/x.py" ruff:docstrings 0 -> 1 (D103 load)',)
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
        """Active only when non-test ``.py`` files outside the eval fixtures were touched."""
        return bool(self.targets(plan))

    def targets(self, plan: StopPlan) -> list[str]:
        """The touched non-test ``.py`` files (memoized per Stop)."""
        if self._targets is None:
            touched = touched_py(plan, self.ctx, self.root)
            self._targets = [rel for rel in touched if not is_test_path(rel, self.ctx)]
        return self._targets

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """The docstring regressions of the touched files: red, warn (context lines) or green."""
        targets = set(self.targets(plan))
        if not targets or plan.head_tree is None:  # an unborn branch has no baseline
            return StageResult(STAGE_NAME, "green")
        found = shared_pass(
            plan, self.ctx, self.root, deadline, git_dir=self.git_dir, gate=self.gate
        )
        if found.error:
            return StageResult(STAGE_NAME, "warn", lines=(found.error,))
        mine = [f for f in found.fails() if _in_docstrings(f) and _file_of(f) in targets]
        if not mine:
            return StageResult(STAGE_NAME, "green")
        lines = tuple(capped([self._line(found, f) for f in mine], MAX_LINES))
        red = any(found.deny_eligible(f.evaluator, self.block) for f in mine)
        return StageResult(STAGE_NAME, "red" if red else "warn", lines=lines)

    def _line(self, found: MetricsPass, finding: ScopeDetail) -> str:
        if finding.evaluator == "ruff_violations":
            detail = ruff_detail(found, self.ctx, self.root, _file_of(finding), FAMILY)
            return ruff_line(finding, FAMILY, detail, found.fix_note(finding))
        path, _, scope = str(finding.scope_key).partition("::")
        return f"{quote_data(path)}::{clip(clean_text(scope), 60)} {STRICT_HINT}"


def _file_of(finding: ScopeDetail) -> str:
    return str(finding.scope_key).partition("::")[0]


def _in_docstrings(finding: ScopeDetail) -> bool:
    """A ``docstrings``-family finding: ruff's ``ruff:docstrings`` count or strict mode."""
    from coding_agent_playbook.grading.static_metrics.ruff_violations import ruff_family

    if finding.evaluator == "ruff_violations":
        return ruff_family(finding.scope_key) == FAMILY
    return finding.evaluator == "docstring_example"


def docstrings_stage(ev: CanonicalEvent, ctx: HandlerContext) -> DocstringsStage | None:
    """The ``docstrings`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``docstrings_stage(stop_event, ctx).name == "docstrings"``.
    """
    if ev.repo is None:
        return None
    return DocstringsStage(
        ctx=ctx,
        root=ev.repo.worktree_root,
        git_dir=ev.repo.git_dir,
        block=block_policy(ctx, HOOK_ID),
    )


@register_hook_handler(
    "docstring_nonregression",
    events=["stop"],
    decisions=_DECISIONS,
    config_schema=CONFIG_SCHEMA,
)
def docstring_nonregression(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``docstrings`` stage alone (no coordinator selected).

    Example: ``docstring_nonregression(stop_after_removing_a_docstring, ctx).decision``.
    """
    stage = docstrings_stage(ev, ctx)
    return None if stage is None else run_alone(stage, ev, ctx)


@register_hook_handler(
    "docstring_nonregression:post_edit",
    events=["post_tool_use"],
    decisions=_DECISIONS,
    config_schema=POST_EDIT_CONFIG_SCHEMA,
)
def docstring_nonregression_post_edit(
    ev: CanonicalEvent, ctx: HandlerContext
) -> HandlerResult | None:
    """The ``python-docstrings`` bucket of the shared D1 ruff call (D100-D107, changed lines).

    Example::

        >>> docstring_nonregression_post_edit(edit_adding_load, ctx).context  # doctest: +SKIP
        ('rule python-docstrings (skill python-coding): "src/x.py:3 D103 Missing docstring in public function"',)
    """
    if ctx.config.get("lint_feedback") is False:
        return None  # switched off: its codes are not in D1 either
    from coding_agent_playbook.hook_runtime.handlers.feedback.ruff_feedback import bucket_feedback

    return bucket_feedback(ev, ctx, rule_id=_RULE)
