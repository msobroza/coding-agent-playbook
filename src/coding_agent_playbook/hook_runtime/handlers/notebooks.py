"""notebook-output-hygiene: warn when agent-edited notebooks keep outputs (specs/prK-hook-pack.md §E.3).

Opt-in, rendered only when the detector found notebooks (``has_notebooks``).

- ``post_tool_use`` (:func:`notebook_hygiene`): after an Edit, Write or
  NotebookEdit of a ``.ipynb`` file, the cells the agent touched (the
  NotebookEdit's ``cell_id``; else those whose source or outputs differ from
  the ``HEAD`` notebook; every cell of an untracked one) that keep outputs
  give one context line per notebook, once per notebook per session. A file
  over ``guard_config.notebooks.max_bytes`` is reported unparsed.
- ``stop`` (stage ``notebooks``, :func:`notebooks_stage`): the same check
  over the ``.ipynb`` files of the working tree's diff, one ``warn`` line in
  the coordinator's combined message. Without the coordinator, the hook's
  own Stop binding (:func:`notebook_hygiene_stop`) gives that line as a note.

Stdlib ``json`` only; ``on_error: open``. The check itself is
``_notebook_check``, shared with ``playbook check-notebooks``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.handlers._notebook_cells import cell_index, notebook_cells
from coding_agent_playbook.hook_runtime.handlers._notebook_check import (
    ADVICE,
    DEFAULT_MAX_CELL_OUTPUT_KB,
    NOTEBOOK_MAX_BYTES,
    NotebookLimits,
    Oversized,
    cell_keys,
    check_cells,
    notebook_line,
    read_notebook,
    touched_cells,
)
from coding_agent_playbook.hook_runtime.handlers._targets import file_write_paths, repo_file
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult, StopPlan

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = [
    "CONFIG_SCHEMA",
    "STAGE_NAME",
    "NotebooksStage",
    "diff_notebooks",
    "limits_of",
    "notebook_hygiene",
    "notebook_hygiene_stop",
    "notebooks_stage",
]

STAGE_NAME: Final = "notebooks"
#: Both bindings read the same keys: a consumer layer merges into each (§A.6).
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "max_cell_output_kb": ConfigKey("integer"),
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "mode": ConfigKey("string", "replace", ("warn",)),  # the stop_gate record: never blocks
}
_SUFFIX: Final = (".ipynb",)
_LISTED: Final = 5


def limits_of(ctx: HandlerContext) -> NotebookLimits:
    """The size cap (``guard_config.notebooks``) and the per-cell budget (this hook's config).

    Example: ``limits_of(ctx).max_cell_output_kb == 64`` with the shipped config.
    """
    table = ctx.cfg.tables.get("notebooks")
    max_bytes = table.get("max_bytes") if isinstance(table, dict) else None
    return NotebookLimits(
        max_bytes=_positive(max_bytes, NOTEBOOK_MAX_BYTES),
        max_cell_output_kb=_positive(
            ctx.config.get("max_cell_output_kb"), DEFAULT_MAX_CELL_OUTPUT_KB
        ),
    )


def _positive(value: object, default: int) -> int:
    """``value`` when a positive integer (never a bool), else ``default``."""
    return value if type(value) is int and value > 0 else default


@register_hook_handler(
    "notebook_hygiene",
    events=["post_tool_use"],
    decisions=["context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def notebook_hygiene(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """One context line per edited notebook whose touched cells keep outputs.

    Example::

        >>> notebook_hygiene(notebook_edit_with_png, ctx).context  # doctest: +SKIP
        ('"nb/a.ipynb": cell c1 keeps outputs (an image/base64 payload). Outputs may ...',)
    """
    if ev.tool is None or ev.repo is None:
        return None
    root, limits = os.path.realpath(ev.repo.worktree_root), limits_of(ctx)
    lines: list[str] = []
    for path in file_write_paths(ev.tool):
        located = repo_file(path, root, ctx.cfg, suffixes=_SUFFIX)
        line = None if located is None else _edited_line(ev.tool, *located, ctx, limits)
        if line is not None and located is not None and ctx.session.once(f"nb:{located[1]}"):
            lines.append(line)
    if not lines:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT,
        hook_id=ctx.hook.id,
        rule_id="notebook_outputs",
        context=tuple(lines),
    )


def _edited_line(
    tool: ToolCall, real: str, rel: str, ctx: HandlerContext, limits: NotebookLimits
) -> str | None:
    found = read_notebook(real, limits)
    if found is None or isinstance(found, Oversized):
        return None if found is None else notebook_line(rel, found, limits)
    return notebook_line(rel, check_cells(found, _touched(tool, found, rel, ctx)), limits)


def _touched(
    tool: ToolCall, cells: list[object], rel: str, ctx: HandlerContext
) -> Collection[str] | None:
    """The NotebookEdit's own cell, else the cells that differ from ``HEAD``."""
    raw = tool.raw_input
    if tool.tool_class is ToolClass.NOTEBOOK_EDIT:
        mode = raw.get("edit_mode") or "replace"
        if mode == "delete":
            return frozenset()
        index = cell_index(cells, raw.get("cell_id")) if mode == "replace" else None
        if index is not None:
            return frozenset({cell_keys(cells)[index]})
    return touched_cells(cells, _head_cells(ctx, rel))


def _head_cells(ctx: HandlerContext, rel: str) -> list[object] | None:
    blob = ctx.git.cat_head(rel)
    return None if blob is None else notebook_cells(blob.decode("utf-8", errors="replace"))


# --- the ``notebooks`` Stop stage -----------------------------------------------------------------


def diff_notebooks(ctx: HandlerContext) -> list[str]:
    """The ``.ipynb`` files the working tree changes or adds over ``HEAD``, sorted.

    Secret paths and frozen eval fixtures are left out.
    """
    changed = {line.path for line in ctx.git.diff_added()} | set(ctx.git.ls_untracked())
    fixtures = ctx.cfg.path_classes.get("eval_fixture")
    return sorted(
        rel
        for rel in changed
        if rel.endswith(_SUFFIX)
        and not ctx.cfg.secret_paths.matches(rel)
        and not (fixtures is not None and fixtures.matches(rel))
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class NotebooksStage:
    """The ``notebooks`` stage of one Stop: deterministic, diff-based, warn only.

    Example::

        >>> notebooks_stage(stop_event, ctx).run(plan, deadline).status  # doctest: +SKIP
        'warn'
    """

    ctx: HandlerContext
    repo_root: str
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "warn"

    def applies(self, plan: StopPlan) -> bool:
        """Active only when the session ledger shows a notebook write."""
        return any(path.endswith(_SUFFIX) for path in plan.touched("writes"))

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """``warn`` with one line naming the notebooks that keep outputs, else ``green``."""
        del plan, deadline  # the diff is git's, not the ledger's; the check is in-process
        limits = limits_of(self.ctx)
        flagged = [rel for rel in diff_notebooks(self.ctx) if self._keeps_outputs(rel, limits)]
        if not flagged:
            return StageResult(STAGE_NAME, "green")
        names = ", ".join(quote_data(rel) for rel in flagged[:_LISTED])
        more = ", …" if len(flagged) > _LISTED else ""
        return StageResult(
            STAGE_NAME, "warn", lines=(f"Notebooks keep outputs: {names}{more}. {ADVICE}",)
        )

    def _keeps_outputs(self, rel: str, limits: NotebookLimits) -> bool:
        found = read_notebook(os.path.join(self.repo_root, rel), limits)
        if found is None or isinstance(found, Oversized):
            return found is not None
        return bool(check_cells(found, touched_cells(found, _head_cells(self.ctx, rel))))


def notebooks_stage(ev: CanonicalEvent, ctx: HandlerContext) -> NotebooksStage | None:
    """The ``notebooks`` stage for ``ev``'s repository (``None`` outside one): the coordinator's factory."""
    return None if ev.repo is None else NotebooksStage(ctx=ctx, repo_root=ev.repo.worktree_root)


@register_hook_handler(
    "notebook_hygiene:stop_stage",
    events=["stop"],
    decisions=["context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def notebook_hygiene_stop(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """The stage alone (no coordinator selected): its warn line as a user note, never a block.

    Example::

        >>> notebook_hygiene_stop(stop_after_notebook_edit, ctx).user_note  # doctest: +SKIP
        '[notebooks] Notebooks keep outputs: "nb/a.ipynb". Outputs may embed data rows; ...'
    """
    stage = notebooks_stage(ev, ctx)
    if stage is None or ctx.hatches.gate_off:
        return None
    ledger = tuple(ctx.ledger.read()) if ctx.ledger is not None else ()
    plan = StopPlan(event=ev, stages=(stage,), ledger=ledger)
    if not stage.applies(plan):
        return None
    result = stage.run(plan, ctx.deadline)
    if not result.lines:
        return None
    note = "\n".join(f"[{STAGE_NAME}] {line}" for line in result.lines)
    return HandlerResult(
        decision=Decision.NONE, hook_id=ctx.hook.id, rule_id=STAGE_NAME, user_note=note
    )
