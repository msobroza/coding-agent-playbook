"""stop-ci-parity-gate's execution stages, ``typecheck`` and ``tests`` (specs/prK-hook-pack.md §E.2).

Both run repo-controlled code (mypy plugins; pytest and ``conftest.py``), so
both are opt-in (``[hooks.stop-ci-parity-gate] stages``) and the coordinator
runs them only when no deterministic stage is red **and** the user approved
this exact stage list on this machine (§B.4). Each runs its rendered
``stop_gate.stages`` record (``project_python -m mypy`` / ``-m pytest -q``,
no path args) through the pinned project interpreter.

- ``typecheck`` is ``skipped`` (``tool_changed``) when ``[tool.mypy] plugins``
  in ``pyproject.toml`` differ from ``HEAD``: a plugin the agent just added is
  code nobody approved.
- ``tests`` runs only when the last message claims completion
  (:func:`._verify_claim.completion_claim`). With ``tests_scope = "touched"`` it
  runs the session's edited test files with ``--no-cov``, because an
  ``addopts`` ``--cov-fail-under`` fails any subset; with none edited it runs
  the whole suite. With coverage-diff-gate on (a ``coverage`` stage record) it
  reads the one full run it shares with the ``coverage`` stage instead
  (``stop.suite``; ``tests_scope`` is then ``all``, §F.1.2).

Red output is trimmed to the failing lines plus the summary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.path_globs import fold_key
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.handlers._verify_claim import completion_claim
from coding_agent_playbook.hook_runtime.handlers.stop_ci_parity_gate import CONFIG_SCHEMA
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult
from coding_agent_playbook.hook_runtime.stop.tools import (
    edited_py,
    runner_of,
    seconds_left,
    stage_command,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.deps import Clock
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.stop.runner import StageRunner
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan
    from coding_agent_playbook.hook_runtime.stop.suite import SuiteOutcome

    type SharedRun = Callable[[StopPlan, float], SuiteOutcome]

__all__ = [
    "PLUGINS_CHANGED",
    "ExecStage",
    "mypy_plugins_changed",
    "shared_verdict",
    "tests_stage",
    "typecheck_stage",
]

PLUGINS_CHANGED: Final = (
    "typecheck skipped: [tool.mypy] plugins changed since HEAD; commit them to re-enable it"
)
_PYPROJECT: Final = "pyproject.toml"
_NO_COV: Final = "--no-cov"
_MAX_LINES: Final = 12
_LINE_CHARS: Final = 160
#: pytest's per-test failure lines; mypy's lines all name ``file:line: error``.
_FAIL_PREFIXES: Final = ("FAILED ", "ERROR ")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecStage:
    """One execution stage of one Stop: its command, and whether this Stop needs it.

    Example::

        >>> typecheck_stage(stop_event, ctx).cost  # doctest: +SKIP
        <StageCost.EXECUTION: 1>
    """

    name: str
    runner: StageRunner
    clock: Clock
    tool: str
    args: tuple[str, ...]
    wanted: bool = True
    plugins_changed: Callable[[], bool] | None = None
    shared: SharedRun | None = None
    cost: StageCost = StageCost.EXECUTION
    needs_diff: bool = True
    mode: str = "block"

    def applies(self, plan: StopPlan) -> bool:
        """``tests`` only when completion is claimed; ``typecheck`` always."""
        return self.wanted

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Green on exit 0; red with the trimmed failures; skipped when it cannot run."""
        if self.plugins_changed is not None and self.plugins_changed():
            return StageResult(
                self.name, "skipped", user_lines=(PLUGINS_CHANGED,), skip_category="tool_changed"
            )
        if self.shared is not None:
            return shared_verdict(self.name, self.shared(plan, deadline))
        left = seconds_left(self.clock, deadline)
        if left <= 0:
            return StageResult(self.name, "skipped", skip_category="timeout")
        run = self.runner.run(self.tool, self.args, timeout=left)
        if run.skip_category:
            return run.skipped(self.name)
        if run.returncode == 0:
            return StageResult(self.name, "green")
        return StageResult(self.name, "red", lines=_failure_lines(run.stdout + run.stderr))


def typecheck_stage(ev: CanonicalEvent, ctx: HandlerContext) -> ExecStage | None:
    """The ``typecheck`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``typecheck_stage(stop_event, ctx).args == ("-m", "mypy")``.
    """
    command = stage_command(ctx.cfg, "typecheck")
    if ev.repo is None or command is None:
        return None
    root, git = ev.repo.worktree_root, ctx.git
    return ExecStage(
        name="typecheck",
        runner=runner_of(ctx, ev.repo),
        clock=ctx.clock,
        tool=command[0],
        args=command[1],
        plugins_changed=lambda: mypy_plugins_changed(root, git),  # only when it runs
    )


def tests_stage(ev: CanonicalEvent, ctx: HandlerContext) -> ExecStage | None:
    """The ``tests`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``tests_stage(stop_saying_tests_pass, ctx).args[-1]`` is a touched test file
    under ``tests_scope = "touched"``.
    """
    command = stage_command(ctx.cfg, "tests")
    repo = ev.repo
    if repo is None or command is None:
        return None
    shared: SharedRun | None = None
    args = command[1]
    if stage_command(ctx.cfg, "coverage") is not None:

        def shared(plan: StopPlan, deadline: float) -> SuiteOutcome:
            from coding_agent_playbook.hook_runtime.stop.suite import shared_suite

            return shared_suite(plan, ctx, repo).outcome(deadline)

    elif HookConfig(ctx.config, CONFIG_SCHEMA).choice("tests_scope", "all") == "touched":
        args = _targeted(args, repo.worktree_root, ctx)
    return ExecStage(
        name="tests",
        runner=runner_of(ctx, repo),
        clock=ctx.clock,
        tool=command[0],
        args=args,
        wanted=completion_claim(ev, ctx.cfg) is not None,
        shared=shared,
    )


def shared_verdict(stage: str, outcome: SuiteOutcome) -> StageResult:
    """``stage``'s verdict from the shared suite run: green, red with its failures, or skipped.

    Example: ``shared_verdict("tests", outcome).status == "red"`` after a failing test.
    """
    problem = outcome.problem
    if problem is not None:
        notes = (problem.advice,) if problem.advice else ()
        return StageResult(stage, "skipped", user_lines=notes, skip_category=problem.category)
    found = outcome.artifacts
    if found is None or not outcome.red:
        return StageResult(stage, "green")
    lines = _failure_lines(outcome.output) if outcome.output.strip() else ()
    junit = found.junit
    summary = f"{junit.failed} failed, {junit.errors} errors (pytest exit {found.returncode})"
    return StageResult(stage, "red", lines=lines or (summary,))


def mypy_plugins_changed(root: str, git: GitPort) -> bool:
    """Whether ``[tool.mypy] plugins`` in ``pyproject.toml`` differ from ``HEAD``'s.

    An unreadable or unparseable side counts as changed: never run unvetted plugins.

    Example: ``mypy_plugins_changed(repo_root, git)`` is ``False`` for an untouched file.
    """
    try:
        with open(os.path.join(root, _PYPROJECT), "rb") as handle:
            current: bytes | None = handle.read()
    except FileNotFoundError:
        current = None
    except OSError:
        return True
    head = git.cat_head(_PYPROJECT)
    if current == head:
        return False
    return _plugins(current) != _plugins(head)


def _plugins(data: bytes | None) -> object:
    """The ``[tool.mypy] plugins`` value of a ``pyproject.toml`` (``None`` when unset)."""
    if data is None:
        return None
    import tomllib  # only when pyproject.toml changed

    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return object()  # never equal: an unparseable side counts as changed
    tool = doc.get("tool")
    mypy = tool.get("mypy") if isinstance(tool, dict) else None
    return mypy.get("plugins") if isinstance(mypy, dict) else None


def _targeted(args: tuple[str, ...], root: str, ctx: HandlerContext) -> tuple[str, ...]:
    """The record's args plus ``--no-cov`` and the session's edited test files, if any."""
    ledger = ctx.ledger.read() if ctx.ledger is not None else []
    tests = ctx.cfg.path_classes.get("test")
    touched = [
        path
        for path in edited_py(ledger)
        if tests is not None
        and tests.matches(fold_key(path, ctx.platform))
        and os.path.isfile(os.path.join(root, path))
    ]
    return (*args, _NO_COV, *touched) if touched else args


def _failure_lines(output: bytes) -> tuple[str, ...]:
    """The failure lines (pytest ``FAILED``/``ERROR``, mypy ``error:``), then the summary."""
    lines = [
        clip(clean_text(line), _LINE_CHARS)
        for line in output.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    failing = [line for line in lines if line.startswith(_FAIL_PREFIXES) or ": error:" in line]
    summary = lines[-1:] if lines and (not failing or lines[-1] != failing[-1]) else []
    return tuple([*failing[: _MAX_LINES - len(summary)], *summary]) or ("(no output)",)
