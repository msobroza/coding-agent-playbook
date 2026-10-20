"""resync-on-detector-input-change: surface newly activated rules mid-session, add-only (specs/prK-hook-pack.md §E.1).

After a successful edit of a detector input (``pyproject.toml``,
``requirements*``, ``Dockerfile``, CI files, a new notebook) or a successful
``uv add``-style command, the cheap comparison (``_detector_inputs``) decides
from ``guard_config.facts`` whether anything the detector reads changed. Only
then does it import ``detector`` (it pulls ``packaging``: a §D.1 branch-local
row), re-run ``detect()`` and evaluate every ``applicability`` row:

- a row that holds now but did not at sync, and is neither in the lockfile's
  ``artifact_id`` set nor an on hook, is injected as context (once per id per
  session) with ``ask the user to run playbook validate && playbook sync``:
  adding ``torch`` names rule ``ml-serialization-security`` and prompt
  ``security-review`` before the risky code is written;
- a row that held at sync and no longer does is reported, never applied.

With ``[hooks] auto_sync`` an add-only change runs ``playbook sync`` as a child
process; a change that would turn anything off never syncs. It builds no
``SyncContext`` (``validation.context`` imports yaml). No debounce: a debounced
detector check would miss a dependency added within 2 s for good (a hook has
no trailing edge), and the comparison alone costs about 5 ms.

A shell call reaches the handler only through an install segment (a shell
tool carries no ``write_paths``), so it declares those programs as its
``argv0s``: the dispatcher's prefilter skips ``ls``, ``pytest`` or ``git
status`` before the handler runs (review finding #7).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler
from coding_agent_playbook.hook_runtime.handlers.protect._detector_inputs import (
    INSTALL_PROGRAMS,
    detector_triggers,
    inputs_changed,
)
from coding_agent_playbook.hook_runtime.handlers.protect._source_changed import (
    context_result,
    run_playbook,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

__all__ = ["resync_on_detector_input_change"]

_ASK: Final = "ask the user to run playbook validate && playbook sync"
_MAX_NAMED: Final = 8
_ID_CHARS: Final = 60


@dataclass(frozen=True, slots=True)
class _Row:
    """One ``guard_config.applicability`` row."""

    kind: str
    id: str
    applies_if: tuple[Mapping[str, Any], ...]
    source: str
    active: bool

    def label(self) -> str:
        return (
            f"{self.kind} {quote_data(self.id, _ID_CHARS)} "
            f"(source {quote_data(self.source, _ID_CHARS)})"
        )


@register_hook_handler(
    "resync_on_detector_input_change",
    events=["post_tool_use"],
    decisions=["context", "none"],
    argv0s=INSTALL_PROGRAMS,
)
def resync_on_detector_input_change(
    ev: CanonicalEvent, ctx: HandlerContext
) -> HandlerResult | None:
    """Context naming the artifacts a detector-input change turns on or off; ``None`` otherwise.

    Example::

        >>> resync_on_detector_input_change(edit_adding_torch, ctx).context[0]  # doctest: +SKIP
        'Detector inputs changed; now applicable but not synced yet: rule "ml-..." ...'
    """
    tool, repo = ev.tool, ev.repo
    facts = ctx.cfg.tables.facts()
    if tool is None or repo is None or not _succeeded(tool) or facts is None:
        return None
    triggers = detector_triggers(tool)
    root = repo.worktree_root
    if not triggers or not inputs_changed(triggers, facts, root, tool.write_paths):
        return None
    turned_on, turned_off = _changes(ctx.cfg, root)
    known = _known_ids(ctx.cfg)
    on = _first_time(ctx, "on", [row for row in turned_on if row.id not in known])
    off = _first_time(ctx, "off", turned_off)
    if not on and not off:
        return None
    return context_result(ctx, _message(ctx, root, on, off), "resync")


def _succeeded(tool: ToolCall) -> bool:
    return tool.response is None or tool.response.ok


def _first_time(ctx: HandlerContext, change: str, rows: Sequence[_Row]) -> list[_Row]:
    """The rows not yet announced this session for ``change`` (``on`` / ``off``)."""
    return [r for r in rows if ctx.session.once(f"resync:{change}:{r.kind}:{r.id}")]


def _changes(cfg: GuardConfig, root: str) -> tuple[list[_Row], list[_Row]]:
    """The rows that hold now but did not at sync, and those that no longer hold."""
    # branch-local: only after a real change
    from coding_agent_playbook.detector import facts as detector

    facts = detector.detect(Path(root))
    turned_on: list[_Row] = []
    turned_off: list[_Row] = []
    for row in _rows(cfg):
        holds = _holds(row, facts, root)
        if holds and not row.active:
            turned_on.append(row)
        elif row.active and not holds:
            turned_off.append(row)
    return turned_on, turned_off


def _holds(row: _Row, facts: Facts, root: str) -> bool:
    # branch-local like the facts import in _changes: it loads packaging
    from coding_agent_playbook.detector.predicate import evaluate_predicate

    try:
        return all(evaluate_predicate(dict(p), facts, repo_root=Path(root)) for p in row.applies_if)
    except ValueError:
        return False  # validate rejects an invalid predicate before sync renders it


def _rows(cfg: GuardConfig) -> list[_Row]:
    return [row for item in cfg.tables.applicability() if (row := _row(item)) is not None]


def _row(item: object) -> _Row | None:
    if not isinstance(item, dict):
        return None
    predicates = item.get("applies_if", [])
    fields = (item.get("kind"), item.get("id"), item.get("source"))
    if not all(isinstance(f, str) for f in fields) or not isinstance(predicates, list):
        return None
    if not all(isinstance(p, dict) for p in predicates):
        return None
    kind, row_id, source = (str(f) for f in fields)
    return _Row(kind, row_id, tuple(predicates), source, item.get("active") is True)


def _known_ids(cfg: GuardConfig) -> frozenset[str]:
    """The lockfile's ``artifact_id`` set plus the on hooks: already rendered."""
    return cfg.tables.protected().artifact_ids | frozenset(cfg.hooks)


def _message(ctx: HandlerContext, root: str, on: Sequence[_Row], off: Sequence[_Row]) -> str:
    lines: list[str] = []
    if on:
        lines.append(f"Detector inputs changed; now applicable but not synced yet: {_named(on)}.")
    if off:
        lines.append(
            f"This change would turn off: {_named(off)}; playbook sync never removes or "
            "relaxes guidance on its own ([hooks] auto_sync is add-only)."
        )
    lines.append(_tail(ctx, root, add_only=bool(on) and not off))
    return "\n".join(lines)


def _tail(ctx: HandlerContext, root: str, *, add_only: bool) -> str:
    """Run ``playbook sync`` for an add-only change under auto-sync; else ask the user."""
    if not (add_only and ctx.cfg.tables.auto_sync()):
        return f"Then {_ASK}."
    try:
        synced = run_playbook(ctx, root, ["sync"])
    except ProcTimeout:
        synced = None
    if synced is not None and synced.ok:
        return "playbook sync ran ([hooks] auto_sync); the generated outputs now include them."
    return f"playbook sync did not complete; {_ASK}."


def _named(rows: Sequence[_Row]) -> str:
    shown = ", ".join(row.label() for row in rows[:_MAX_NAMED])
    hidden = len(rows) - _MAX_NAMED
    return f"{shown} and {hidden} more" if hidden > 0 else shown
