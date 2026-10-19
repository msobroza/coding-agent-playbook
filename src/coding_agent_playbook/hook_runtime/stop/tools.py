"""What the tool-backed Stop stages share (specs/prK-lifecycle-hooks.md §D.5.2 rule 4, §D.6.3).

- :func:`stage_command`: a stage's logical tool and args come from its
  ``guard_config.stop_gate.stages`` record, rendered at sync, never from a
  file the agent can edit at run time;
- :func:`runner_of`: the dispatch's ``StageRunner`` (``RuntimeDeps.stage_runner``
  in tests, else the ``machine.json`` pins);
- :func:`seconds_left`: a stage's remaining time, so no tool outlives it;
- :func:`edited_py`: the ledger's Python edits, the evidence verify-claim,
  ``tests`` and ``quality-metrics`` read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.deps import Clock
    from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.runner import StageRunner

__all__ = [
    "READ_ONLY_CLASSES",
    "edited_py",
    "py_edit_indexes",
    "runner_of",
    "seconds_left",
    "stage_command",
]

#: Ledger tool classes that never write: their lines are not edits.
READ_ONLY_CLASSES: Final = frozenset({"read", "search", "web"})
_PY: Final = "py"


def stage_command(cfg: GuardConfig, name: str) -> tuple[str, tuple[str, ...]] | None:
    """The ``(tool, args)`` of stage ``name``'s rendered record, or ``None`` without one.

    Example::

        >>> stage_command(cfg, "lint")  # doctest: +SKIP
        ('ruff', ('check', '--output-format=json', '.'))
    """
    for record in cfg.tables.stop_gate().stages:
        if record.name == name and record.tool is not None and record.args is not None:
            return record.tool, record.args
    return None


def runner_of(ctx: HandlerContext, repo: RepoInfo) -> StageRunner:
    """The dispatch's stage runner: the injected one, else the worktree's pinned tools.

    Example: ``runner_of(ctx, ev.repo).run("ruff", ["check", "."], timeout=2.0)``.
    """
    injected = None if ctx.deps is None else ctx.deps.stage_runner
    if injected is not None:
        return injected
    from coding_agent_playbook.hook_runtime.stop.runner import PinnedStageRunner

    return PinnedStageRunner.for_repo(ctx.proc, repo)


def seconds_left(clock: Clock, deadline: float) -> float:
    """The time a stage may still spend; ``0.0`` once ``deadline`` passed.

    Example: ``seconds_left(FakeClock(mono=10.0), 12.5) == 2.5``.
    """
    return max(0.0, deadline - clock.monotonic())


def py_edit_indexes(ledger: Sequence[Mapping[str, Any]]) -> list[int]:
    """The indexes of the ledger lines that wrote a Python file (``cats`` holds ``py``).

    Example: ``py_edit_indexes([{"tc": "edit", "cats": ["py"]}]) == [0]``.
    """
    return [
        index
        for index, line in enumerate(ledger)
        if line.get("tc") not in READ_ONLY_CLASSES and _PY in _strings(line.get("cats"))
    ]


def edited_py(ledger: Sequence[Mapping[str, Any]]) -> list[str]:
    """The repo-relative ``.py`` paths the session's write lines name, in first-seen order.

    Example: ``edited_py([{"tc": "edit", "paths": ["src/a.py"], "cats": ["py"]}]) == ["src/a.py"]``.
    """
    found: dict[str, None] = {}
    for index in py_edit_indexes(ledger):
        line = ledger[index]
        for path in (*_strings(line.get("paths")), *_strings(line.get("writes"))):
            if path.endswith(".py") and not path.startswith("<"):
                found[path] = None
    return list(found)


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
