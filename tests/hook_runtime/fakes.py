"""Named fakes for the hook runtime's seams (specs/prK-lifecycle-hooks.md §D.9).

Each fake stands in for one ``RuntimeDeps`` port, so a test passes it in and
never patches a module:

- ``FakeProc`` for ``proc.SubprocessProc``: replays scripted results, records
  every call, and raises ``AssertionError("unexpected subprocess: <argv0>")``
  for a call nobody scripted, so a stray spawn fails loudly.
- ``FakeGit`` for ``git.SafeGit``: scripted answers, every call recorded.
- ``FakeClock`` for ``deps.SystemClock``: time moves only when told to.
- ``FakeTrustStore`` for ``security.trust.TrustStore``: in-memory approvals.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.proc import ProcResult, ProcTimeout

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.git import AddedLine, Fingerprint
    from coding_agent_playbook.security.trust import HandlerApproval

type ArgvMatch = Sequence[str] | Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class FakeCall:
    """One recorded ``FakeProc.run`` call."""

    argv: tuple[str, ...]
    timeout: float
    env: Mapping[str, str] | None
    input: bytes | None
    cwd: str | None


@dataclass
class _Scripted:
    match: ArgvMatch
    result: ProcResult | None  # None: the call times out


def _matches(match: ArgvMatch, argv: tuple[str, ...]) -> bool:
    """A callable decides; a sequence needs ``argv[0]`` (or its basename), then its rest in order."""
    if callable(match):
        return match(argv)
    head, *rest = match
    if not argv or head not in (argv[0], os.path.basename(argv[0])):
        return False
    remaining = iter(argv[1:])
    return all(token in remaining for token in rest)  # in-order subsequence


@dataclass
class FakeProc:
    """In-memory ``ProcPort``: scripted results, recorded calls, loud on surprises.

    ``script(["git", "status"], stdout=b"...")`` answers any call whose argv
    starts with ``git`` (or a path ending in it) and contains ``status`` later,
    in order (so the hardening flags ``SafeGit`` prepends do not get in the
    way); the first matching script wins, and scripts are reusable.
    ``programs`` is what ``which`` finds.
    """

    programs: dict[str, str] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)
    _scripts: list[_Scripted] = field(default_factory=list)

    def script(
        self,
        match: ArgvMatch,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        """Answer calls matching ``match`` (see the class docstring)."""
        result = None if timeout else ProcResult(("<scripted>",), returncode, stdout, stderr)
        self._scripts.append(_Scripted(match, result))

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        """Replay the first matching script, or fail the test."""
        command = tuple(argv)
        self.calls.append(
            FakeCall(command, timeout, None if env is None else dict(env), input, cwd)
        )
        scripted = next((s for s in self._scripts if _matches(s.match, command)), None)
        if scripted is None:
            raise AssertionError(f"unexpected subprocess: {command[0] if command else '<empty>'}")
        if scripted.result is None:
            raise ProcTimeout(command[0], timeout)
        return ProcResult(command, *_payload(scripted.result))

    def which(self, name: str, *, path: str | None = None) -> str | None:
        """``programs[name]``, else ``None``; ``path`` is ignored."""
        return self.programs.get(name)


def _payload(result: ProcResult) -> tuple[int, bytes, bytes]:
    return result.returncode, result.stdout, result.stderr


@dataclass
class FakeGit:
    """In-memory ``GitPort``: each answer is a field; ``errors`` raises per method name."""

    head_tree_id: str | None = None
    fingerprint_value: Fingerprint | None = None
    added: tuple[AddedLine, ...] = ()
    head_blobs: dict[str, bytes] = field(default_factory=dict)
    untracked: tuple[str, ...] = ()
    errors: dict[str, Exception] = field(default_factory=dict)
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def _record(self, method: str, *args: str) -> None:
        self.calls.append((method, args))
        if method in self.errors:
            raise self.errors[method]

    def head_tree(self) -> str | None:
        self._record("head_tree")
        return self.head_tree_id

    def fingerprint(self) -> Fingerprint | None:
        self._record("fingerprint")
        return self.fingerprint_value

    def diff_added(self) -> tuple[AddedLine, ...]:
        self._record("diff_added")
        return self.added

    def cat_head(self, repo_rel: str) -> bytes | None:
        self._record("cat_head", repo_rel)
        return self.head_blobs.get(repo_rel)

    def ls_untracked(self) -> tuple[str, ...]:
        self._record("ls_untracked")
        return self.untracked


@dataclass
class FakeClock:
    """A clock that moves only through :meth:`advance`."""

    now: float = 1_791_973_800.0  # 2026-10-14T10:30:00Z
    mono: float = 1_000.0

    def monotonic(self) -> float:
        return self.mono

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move both clocks forward by ``seconds``."""
        self.mono += seconds
        self.now += seconds


@dataclass
class FakeTrustStore:
    """In-memory ``TrustPort``, with ``security.trust.TrustStore``'s matching rules."""

    handlers: dict[str, HandlerApproval] = field(default_factory=dict)
    executions: set[str] = field(default_factory=set)

    def allows_handler(self, hook_id: str, wanted: HandlerApproval) -> bool:
        approved = self.handlers.get(hook_id)
        return approved is not None and approved.same_code(wanted)

    def allows_execution(self, stages_sha256: str) -> bool:
        return stages_sha256 in self.executions
