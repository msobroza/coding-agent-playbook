"""The one way a Stop stage runs a tool (specs/prK-lifecycle-hooks.md §D.5.2 rule 4, §D.8.3).

A stage record names a **logical** tool (``ruff``, ``project_python``) and its
args; ``guard_config.json`` never holds an absolute path. The program comes
from the per-worktree ``machine.json`` pins that every write-mode sync
rewrites, never from a file the agent can edit at run time:

- no ``machine.json`` (a fresh worktree) or no pin for the tool: the stage is
  ``toolchain_missing``, with one line of advice for the **user**;
- a program whose stat signature changed since sync: ``tool_changed``, so an
  overwritten binary is never run and the stage is never reported green;
- otherwise one ``proc.run`` with the stage's timeout; a timeout is
  ``timeout``. Every outcome is a :class:`ToolRun`, never an exception.

``FakeStageRunner`` (tests) scripts :class:`StageRunner` per logical tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.stop.output import NO_PINS_ADVICE, toolchain_advice
from coding_agent_playbook.hook_runtime.stop.stages import StageResult

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config.pin import MachinePins, ToolPin
    from coding_agent_playbook.hook_runtime.dispatch.deps import ProcPort
    from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo
    from coding_agent_playbook.hook_runtime.stop.stages import SkipCategory

__all__ = ["PinnedStageRunner", "StageRunner", "ToolRun"]


@dataclass(frozen=True, slots=True)
class ToolRun:
    """One tool invocation's result, or why it did not run (``skip_category``, ``advice``).

    Example::

        >>> ToolRun("ruff", skip_category="timeout").skipped("lint").verified
        False
    """

    tool: str
    returncode: int | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    skip_category: SkipCategory = ""
    advice: str = ""

    def skipped(self, stage: str) -> StageResult:
        """This run as ``stage``'s skipped result; the advice goes to the user."""
        user_lines = (self.advice,) if self.advice else ()
        return StageResult(
            stage, "skipped", user_lines=user_lines, skip_category=self.skip_category or "crash"
        )


class StageRunner(Protocol):
    """Runs a stage's logical tool with its args; ``FakeStageRunner`` scripts it.

    ``cwd`` defaults to the worktree root; the lint baseline runs in an export.
    ``env`` replaces the child environment when given (the shared suite points
    ``COVERAGE_FILE`` into the state dir, specs/prK-hook-pack.md §F.1.2).
    """

    def run(
        self,
        tool: str,
        args: Sequence[str],
        *,
        timeout: float,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ToolRun: ...


class PinnedStageRunner:
    """:class:`StageRunner` over the ``machine.json`` pins and ``proc.run``.

    ``pins`` is read once, on the first call (``None``: no ``machine.json``).

    Example::

        >>> runner = PinnedStageRunner.for_repo(deps.proc, ev.repo)  # doctest: +SKIP
        >>> runner.run("ruff", ["check", "."], timeout=2.0).returncode
        0
    """

    def __init__(self, proc: ProcPort, *, cwd: str, pins: Callable[[], MachinePins | None]) -> None:
        self._proc = proc
        self._cwd = cwd
        self._read_pins = pins
        self._pins: list[MachinePins | None] = []

    @classmethod
    def for_repo(cls, proc: ProcPort, repo: RepoInfo) -> PinnedStageRunner:
        """The runner of ``repo``'s worktree: its pins, its root as the working directory."""
        from coding_agent_playbook.hook_runtime.config.pin import read_machine_pins

        return cls(
            proc, cwd=repo.worktree_root, pins=lambda: read_machine_pins(git_dir=repo.git_dir)
        )

    def run(
        self,
        tool: str,
        args: Sequence[str],
        *,
        timeout: float,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ToolRun:
        """Run ``tool``'s pinned argv plus ``args`` within ``timeout`` seconds, in ``cwd``."""
        pin = self._pin(tool)
        if isinstance(pin, ToolRun):
            return pin
        try:
            done = self._proc.run(
                [*pin.argv, *args], timeout=timeout, cwd=cwd or self._cwd, env=env
            )
        except ProcTimeout:
            return ToolRun(tool, skip_category="timeout")
        except OSError:  # the pinned program vanished between the stat and the spawn
            advice = toolchain_advice(tool, "not found on the pinned path")
            return ToolRun(tool, skip_category="toolchain_missing", advice=advice)
        return ToolRun(tool, done.returncode, done.stdout, done.stderr)

    def _pin(self, tool: str) -> ToolPin | ToolRun:
        if not self._pins:
            self._pins.append(self._read_pins())
        pins = self._pins[0]
        if pins is None:
            return ToolRun(tool, skip_category="toolchain_missing", advice=NO_PINS_ADVICE)
        pin = pins.tool(tool)
        if pin is None:
            advice = toolchain_advice(tool, "not found on the pinned path")
            return ToolRun(tool, skip_category="toolchain_missing", advice=advice)
        if not pin.unchanged():
            advice = toolchain_advice(tool, "changed since sync")
            return ToolRun(tool, skip_category="tool_changed", advice=advice)
        return pin
