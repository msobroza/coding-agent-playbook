"""The single output write and the event watchdog (specs/prK-lifecycle-hooks.md §D.1, §D.4).

A harness parses exactly one JSON object from stdout, so a dispatch writes its
output once. Two writers race for that write: the main path, when every
handler has returned, and the watchdog, when the event's deadline
(``guard_config.deadlines_ms``) passes first. :class:`OutputGate` lets only the
first through. The watchdog then writes the failure-policy result for the
handlers still pending (results already computed are kept), logs one
``degraded`` line and ends the process with ``deps.exit`` (``os._exit``), so a
hung handler can never let the harness time out into a fail-open.

The timer comes from ``deps.timer_factory`` (a daemon ``threading.Timer``) and
works on POSIX and Windows alike (no ``SIGALRM``). Tests pass a synchronous
fake timer and a fake ``exit`` that raises.
"""

from __future__ import annotations

import _thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TextIO

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps, TimerHandle
    from coding_agent_playbook.hook_runtime.harness.wire import WireOutput

__all__ = ["OutputGate", "Watchdog"]


class OutputGate:
    """Lets exactly one :class:`WireOutput` through to the real stdout and stderr.

    ``out`` / ``err`` may be ``None`` (``simulate`` and in-process tests read
    the returned output instead). ``_thread`` gives a lock without importing
    ``threading`` on the hot path.

    Example::

        >>> gate = OutputGate(None, None)
        >>> gate.write(WireOutput()), gate.write(WireOutput())  # doctest: +SKIP
        (True, False)
    """

    def __init__(self, out: TextIO | None, err: TextIO | None) -> None:
        self._out = out
        self._err = err
        self._lock = _thread.allocate_lock()
        self._written: WireOutput | None = None

    @property
    def written(self) -> WireOutput | None:
        """What went out, or ``None`` before the write."""
        return self._written

    def write(self, output: WireOutput) -> bool:
        """Write ``output`` unless something was already written; True when this call wrote."""
        with self._lock:
            if self._written is not None:
                return False
            self._written = output
            _emit(self._out, output.stdout)
            _emit(self._err, output.stderr)
            return True

    def note(self, text: str) -> None:
        """One internal note on stderr (after the write; Claude shows exit-0 stderr to no model)."""
        _emit(self._err, f"{text}\n")


def _emit(stream: TextIO | None, text: str) -> None:
    if stream is None or not text:
        return
    try:
        stream.write(text)
        stream.flush()
    except (OSError, ValueError):
        return  # a closed pipe: the harness is gone and nothing can be reported


class Watchdog:
    """Arms one deadline timer for a dispatch; :meth:`cancel` once the main path has written.

    ``fallback`` builds the failure-policy output at fire time; ``on_fire`` runs
    after the watchdog's write (the ``degraded`` decision-log line).

    Example::

        >>> dog = Watchdog(deps, gate, fallback=lambda: WireOutput())  # doctest: +SKIP
        >>> dog.arm(2.0); ...; dog.cancel()
    """

    def __init__(
        self,
        deps: RuntimeDeps,
        gate: OutputGate,
        *,
        fallback: Callable[[], WireOutput],
        on_fire: Callable[[], None] = lambda: None,
    ) -> None:
        self._deps = deps
        self._gate = gate
        self._fallback = fallback
        self._on_fire = on_fire
        self._timer: TimerHandle | None = None

    def arm(self, seconds: float) -> None:
        """Start the timer: :meth:`fire` runs after ``seconds`` unless cancelled first."""
        self._timer = self._deps.timer_factory(max(0.0, seconds), self.fire)
        self._timer.start()

    def fire(self) -> None:
        """Write the failure-policy output if nothing went out yet, then end the process."""
        output = self._fallback()
        if not self._gate.write(output):
            return  # the main path won the race: nothing to do
        try:
            self._on_fire()
        finally:
            self._deps.exit(output.exit_code)

    def cancel(self) -> None:
        """Stop the timer and wait for its thread, so no timer outlives the dispatch."""
        timer, self._timer = self._timer, None
        if timer is None:
            return
        timer.cancel()
        timer.join(1.0)
