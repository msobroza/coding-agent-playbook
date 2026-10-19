"""Named fakes for the hook seams of the K10 tools (specs/prK-hook-pack.md §F.1.2, §F.4.2).

- ``FakeSuiteFactory`` for ``RuntimeDeps.suite_handle``: every shared suite
  run gets a ``FakeProjectHandle`` serving canned ``RunArtifacts`` (or one
  raising ``problem``), so pytest is never executed; ``specs`` keeps what each
  run would have executed and ``handles`` each handle for its ``runs`` count.
- ``FakeCz`` for the pinned commitizen behind ``RuntimeDeps.proc``: ``cz check
  --message`` / ``--rev-range`` answered by a verdict function, every argv
  recorded; any other program fails the test, like ``FakeProc``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.dispatch.proc import ProcResult, ProcTimeout
from tests.fakes import FakeProjectHandle, empty_run

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle, RunArtifacts
    from coding_agent_playbook.hook_runtime.stop.suite import SuiteSpec

__all__ = ["CZ_REJECTION", "FailingProjectHandle", "FakeCz", "FakeSuiteFactory"]


@dataclass
class FailingProjectHandle(FakeProjectHandle):
    """A ``FakeProjectHandle`` whose run raises ``problem`` (a timeout, a missing pytest-cov)."""

    problem: Exception = field(default_factory=lambda: RuntimeError("suite crashed"))

    def _run_once(self) -> RunArtifacts:
        self.runs += 1
        raise self.problem


@dataclass
class FakeSuiteFactory:
    """``RuntimeDeps.suite_handle``: canned artifacts per shared run, never a real suite.

    ``problem`` makes every handle's run raise it instead.
    """

    artifacts: RunArtifacts = field(default_factory=empty_run)
    problem: Exception | None = None
    specs: list[SuiteSpec] = field(default_factory=list)
    handles: list[FakeProjectHandle] = field(default_factory=list)

    def __call__(self, spec: SuiteSpec) -> ProjectHandle:
        self.specs.append(spec)
        handle = self._handle(spec)
        self.handles.append(handle)
        return handle

    def _handle(self, spec: SuiteSpec) -> FakeProjectHandle:
        if self.problem is None:
            return FakeProjectHandle(
                root=spec.root,
                test_cmd=[spec.tool],
                report_dir=spec.report_dir,
                artifacts=self.artifacts,
            )
        return FailingProjectHandle(
            root=spec.root, test_cmd=[spec.tool], report_dir=spec.report_dir, problem=self.problem
        )

    @property
    def runs(self) -> int:
        """Suite runs over every handle made."""
        return sum(handle.runs for handle in self.handles)


#: What ``cz check`` prints on a rejected message (commitizen 3.x, abridged).
CZ_REJECTION = (
    b"commit validation: failed!\n"
    b"please enter a commit message in the commitizen format.\n"
    b'commit "": "Add thing."\n'
    b"pattern: (?s)(build|ci|docs|feat|fix|perf|refactor|style|test|chore|revert|bump)"
    b"(\\(\\S+\\))?!?:( [^\\n\\r]+)((\\n\\n.*)|(\\s*))?$\n"
)


def _conventional(message: str) -> bool:
    head = message.split("\n", 1)[0]
    kind = head.split(":", 1)[0].split("(", 1)[0].rstrip("!")
    return ":" in head and kind in {"feat", "fix", "docs", "test", "refactor", "chore", "ci"}


@dataclass
class FakeCz:
    """In-memory ``ProcPort`` for the pinned ``cz``: answers ``cz check``, records every argv.

    ``accepts(message)`` decides a ``--message`` check (default: a conventional
    subject); ``rejected_ranges`` are the ``--rev-range`` values that fail;
    ``timeout`` makes every call time out. ``messages`` lists each message
    checked, ``ranges`` each range, in order.
    """

    accepts: Callable[[str], bool] = _conventional
    rejected_ranges: frozenset[str] = frozenset()
    timeout: bool = False
    calls: list[tuple[str, ...]] = field(default_factory=list)
    cwds: list[str | None] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        command = tuple(argv)
        if not command or os.path.basename(command[0]) != "cz":
            raise AssertionError(f"unexpected subprocess: {command[0] if command else '<empty>'}")
        self.calls.append(command)
        self.cwds.append(cwd)
        if self.timeout:
            raise ProcTimeout(command[0], timeout)
        args = command[1:]
        ok = (
            self.accepts(args[2])
            if args[:2] == ("check", "--message")
            else args[2] not in self.rejected_ranges
        )
        return ProcResult(command, 0 if ok else 1, b"" if ok else CZ_REJECTION)

    def which(self, name: str, *, path: str | None = None) -> str | None:
        return None

    @property
    def messages(self) -> list[str]:
        """The message of every ``cz check --message`` call, in order."""
        return [call[3] for call in self.calls if call[1:3] == ("check", "--message")]

    @property
    def ranges(self) -> list[str]:
        """The range of every ``cz check --rev-range`` call, in order."""
        return [call[3] for call in self.calls if call[1:3] == ("check", "--rev-range")]
