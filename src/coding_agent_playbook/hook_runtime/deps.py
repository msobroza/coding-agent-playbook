"""Every external effect of the hook runtime, behind one injectable value (specs/prK-lifecycle-hooks.md §D.9).

``RuntimeDeps`` is passed into the dispatcher, so a test swaps a seam by
passing a fake (``FakeProc``, ``FakeGit``, ``FakeClock``, ``FakeTrustStore``)
instead of patching a module. The ports are structural ``Protocol``s: K1's
``security.trust.TrustStore`` satisfies :class:`TrustPort` without this
module importing it, and :class:`~coding_agent_playbook.hook_runtime.git.GitPort`
lives beside its one real implementation, ``SafeGit``.

Import-light: ``threading`` is imported only when a real timer is made.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NoReturn, Protocol

from coding_agent_playbook.hook_runtime.proc import SubprocessProc

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from typing import TextIO

    from coding_agent_playbook.hook_runtime.git import GitPort
    from coding_agent_playbook.hook_runtime.proc import ProcResult
    from coding_agent_playbook.hook_runtime.state import StateStore
    from coding_agent_playbook.security.trust import HandlerApproval

__all__ = [
    "Clock",
    "ProcPort",
    "RuntimeDeps",
    "SystemClock",
    "TimerFactory",
    "TimerHandle",
    "TrustPort",
    "thread_timer",
]


class ProcPort(Protocol):
    """Starts child processes and finds programs; ``proc.SubprocessProc`` is the real one."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult: ...

    def which(self, name: str, *, path: str | None = None) -> str | None: ...


class TrustPort(Protocol):
    """Reads the user's approvals of repo- and overlay-controlled code (§B.4); read-only here."""

    def allows_handler(self, hook_id: str, wanted: HandlerApproval) -> bool: ...

    def allows_execution(self, stages_sha256: str) -> bool: ...


class Clock(Protocol):
    """``monotonic`` for budgets and deadlines, ``time`` (epoch seconds) for timestamps."""

    def monotonic(self) -> float: ...

    def time(self) -> float: ...


class TimerHandle(Protocol):
    """The part of ``threading.Timer`` the watchdog uses."""

    @property
    def daemon(self) -> bool: ...

    def start(self) -> None: ...

    def cancel(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...


type TimerFactory = Callable[[float, Callable[[], None]], TimerHandle]


class SystemClock:
    """The real clocks.

    Example::

        >>> SystemClock().time() > 0
        True
    """

    def monotonic(self) -> float:
        """``time.monotonic()``."""
        return time.monotonic()

    def time(self) -> float:
        """``time.time()``."""
        return time.time()


def thread_timer(interval: float, function: Callable[[], None]) -> TimerHandle:
    """A daemon ``threading.Timer``: it never keeps a finished hook process alive.

    Example::

        >>> timer = thread_timer(5.0, lambda: None); timer.start(); timer.cancel()
    """
    import threading  # lazy: only the watchdog needs a thread

    timer = threading.Timer(interval, function)
    timer.daemon = True
    return timer


def _environ_snapshot() -> dict[str, str]:
    return dict(os.environ)


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeDeps:
    """The dispatcher's seams; every default is the real effect.

    ``env`` is a snapshot of the hook process environment, the only place
    escape hatches are read from (§D.7). ``git``, ``state`` and ``trust`` are
    ``None`` until the dispatcher builds them for the event's repository (a
    ``SafeGit`` over ``proc``, the per-worktree ``StateStore``, the user-local
    trust store); a test passes fakes instead. ``exit`` ends the process from
    the watchdog without unwinding (``os._exit``); ``timer_factory`` makes its
    timer. ``home`` and ``platform`` feed path normalization.

    Example::

        >>> RuntimeDeps(env={"CI": "true"}).env["CI"]
        'true'
    """

    env: Mapping[str, str] = field(default_factory=_environ_snapshot)
    clock: Clock = field(default_factory=SystemClock)
    proc: ProcPort = field(default_factory=SubprocessProc)
    git: GitPort | None = None
    state: StateStore | None = None
    trust: TrustPort | None = None
    out: TextIO | None = None
    err: TextIO | None = None
    exit: Callable[[int], NoReturn] = os._exit
    timer_factory: TimerFactory = thread_timer
    home: str = field(default_factory=lambda: os.path.expanduser("~"))
    platform: str = sys.platform
