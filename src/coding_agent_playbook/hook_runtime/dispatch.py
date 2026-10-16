"""The dispatch pipeline: one harness event in, one decided output out (specs/prK-lifecycle-hooks.md §D.1).

:func:`run_event` is the nine steps every hook process runs:

1. the ``PLAYBOOK_HOOKS=off`` gate (read only from the hook process env);
2. stdin, capped at 16 MiB (the rest drained unread), parsed by the
   harness's parser: a foreign payload is inert, a ``ContractFault`` goes to
   the failure policy, an event outside git is inert (K-12);
3. ``guard_config.json``, trusted only through its lockfile digest
   (a ``ConfigFault`` asks once per session);
4. selection (event, harness, ``PLAYBOOK_HOOKS_DISABLE``, matcher), ordered
   ``(class rank, priority, id)``;
5. the handlers, under the watchdog and the per-hook failure policy; the
   first guard deny ends the fan-out;
6. ``combine``: event support, ask degradation, caps, plus deferred notes;
7. the harness renderer, and the one locked write;
8. the decision log, the asked set, the ledger and the sweep, after the write;
9. the exit code (``0`` or ``DENY_EXIT``), returned to ``cli``.

Steps 1-2 and the paths that never reach a config live here; steps 3-9 in
``_pipeline``. Everything external comes from ``RuntimeDeps``, so tests and
``simulate`` run this exact pipeline with fakes and ephemeral state.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, BinaryIO

from coding_agent_playbook.hook_runtime._decision_log import DISPATCHER_ID, DecisionLog, LogLine
from coding_agent_playbook.hook_runtime._faults import (
    contract_fault_results,
    degraded_lines,
    fault_event,
)
from coding_agent_playbook.hook_runtime._pipeline import Shared, run_configured
from coding_agent_playbook.hook_runtime._tail import DispatchTrace, Responder
from coding_agent_playbook.hook_runtime.escape import HOOKS_VAR, read_escape_hatches, settings_files
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.harness import (
    STDIN_CAP_BYTES,
    ContractFault,
    ForeignPayload,
    ParseContext,
    WireOutput,
)
from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.hook_runtime.session import SessionState
from coding_agent_playbook.hook_runtime.state import StateStore
from coding_agent_playbook.hook_runtime.watchdog import OutputGate

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.harness import ParseOutcome

__all__ = ["DispatchTrace", "dispatch_event", "read_stdin", "run_event"]


def run_event(
    event: EventName,
    harness: Harness,
    stdin: bytes | BinaryIO,
    deps: RuntimeDeps,
    *,
    project_dir: str | None = None,
    argv_problem: str | None = None,
    asynchronous: bool = False,
) -> WireOutput:
    """Run the pipeline for one event and return the output it wrote (or would write).

    ``argv_problem`` is a dispatch-argv error from ``cli``: the event then
    goes to the failure policy as a ``ContractFault``, never to an exit 2.
    ``asynchronous`` is the ``--async`` ``post_tool_use`` dispatch (OQ-19).

    Example::

        >>> run_event(EventName.PRE_TOOL_USE, Harness.CLAUDE_CODE, payload, deps).exit_code
        ... # doctest: +SKIP
        10
    """
    trace = dispatch_event(
        event,
        harness,
        stdin,
        deps,
        project_dir=project_dir,
        argv_problem=argv_problem,
        asynchronous=asynchronous,
    )
    return trace.wire


def dispatch_event(
    event: EventName,
    harness: Harness,
    stdin: bytes | BinaryIO,
    deps: RuntimeDeps,
    *,
    project_dir: str | None = None,
    argv_problem: str | None = None,
    canary: bool = False,
    asynchronous: bool = False,
) -> DispatchTrace:
    """:func:`run_event`, returning the whole :class:`DispatchTrace` (``simulate``, canaries).

    ``canary`` tags every decision line ``canary: true`` (doctor / heartbeat self-tests).
    ``asynchronous`` runs only the async-routed handlers and writes nothing; it
    is honoured on ``post_tool_use`` only (``cli`` turns it into a fault elsewhere).

    Example::

        >>> dispatch_event(EventName.STOP, Harness.CLAUDE_CODE, b"{}", deps).written  # doctest: +SKIP
        False
    """
    run = _Dispatch(
        event,
        harness,
        deps,
        project_dir=project_dir,
        canary=canary,
        asynchronous=asynchronous and event is EventName.POST_TOOL_USE,
    )
    return run.execute(stdin, argv_problem)


def read_stdin(stdin: bytes | BinaryIO) -> tuple[bytes, bool]:
    """At most 16 MiB of the payload and whether it was cut; the rest is drained unread.

    Draining keeps the OpenCode shim from an EPIPE on a huge payload (§D.1).

    Example::

        >>> read_stdin(b"{}")
        (b'{}', False)
    """
    if isinstance(stdin, bytes):
        return stdin[:STDIN_CAP_BYTES], len(stdin) > STDIN_CAP_BYTES
    data = stdin.read(STDIN_CAP_BYTES + 1)
    if len(data) <= STDIN_CAP_BYTES:
        return data, False
    while stdin.read(1 << 16):
        pass
    return data[:STDIN_CAP_BYTES], True


class _Dispatch:
    """Steps 1-2 of one dispatch, and the decisions made before any config loads."""

    def __init__(
        self,
        event: EventName,
        harness: Harness,
        deps: RuntimeDeps,
        *,
        project_dir: str | None,
        canary: bool,
        asynchronous: bool = False,
    ) -> None:
        self.event = event
        self.harness = harness
        self.deps = deps
        self.project_dir = project_dir
        self.canary = canary
        self.asynchronous = asynchronous
        self.responder = Responder(harness, OutputGate(deps.out, deps.err))
        self.started = deps.clock.monotonic()

    @property
    def root_guess(self) -> str:
        """The project root before the payload names one: ``--project-dir``, the env, the cwd."""
        return self.project_dir or self.deps.env.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    def execute(self, stdin: bytes | BinaryIO, argv_problem: str | None) -> DispatchTrace:
        """Steps 1-2, then steps 3-9 for an event inside a repository."""
        hatches = read_escape_hatches(self.deps.env, settings_files=self._settings_files)
        payload, truncated = read_stdin(stdin)
        if hatches.hooks_off:
            self._log_hooks_off(payload)
            return DispatchTrace(wire=WireOutput())
        outcome = self._parse(payload, truncated, argv_problem)
        if isinstance(outcome, ForeignPayload):
            return DispatchTrace(wire=WireOutput())
        if isinstance(outcome, ContractFault):
            if self.asynchronous:
                return DispatchTrace(wire=WireOutput())  # the synchronous dispatch reports it
            return self._contract_fault(outcome)
        if outcome.repo is None:
            return DispatchTrace(wire=WireOutput())  # hooks are git-only in v1 (K-12)
        shared = Shared(
            deps=self.deps,
            responder=self.responder,
            started=self.started,
            canary=self.canary,
            asynchronous=self.asynchronous,
        )
        return run_configured(outcome, outcome.repo, hatches, shared)

    def _settings_files(self) -> Sequence[Path]:
        root = self.root_guess
        return settings_files(
            find_repo(root), project_dir=root, env=self.deps.env, home=self.deps.home
        )

    def _parse(self, payload: bytes, truncated: bool, argv_problem: str | None) -> ParseOutcome:
        if argv_problem is not None:
            return ContractFault(event=self.event, problem=argv_problem)
        ctx = ParseContext(
            argv_event=self.event,
            env=self.deps.env,
            project_dir=self.project_dir,
            home=self.deps.home,
            platform=self.deps.platform,
            truncated=truncated,
        )
        if self.harness is Harness.OPENCODE:
            from coding_agent_playbook.hook_runtime.harness.opencode import parse_opencode

            return parse_opencode(payload, ctx)
        from coding_agent_playbook.hook_runtime.harness.claude import parse_claude

        return parse_claude(payload, ctx)

    def _contract_fault(self, fault: ContractFault) -> DispatchTrace:
        """Ask on ``pre_tool_use`` (deny unattended), nothing elsewhere; one degraded line."""
        ev = self._bare_event(fault.session_id)
        results = contract_fault_results(self.event, fault.problem)
        combined, wire = self.responder.respond(ev, results)
        lines = degraded_lines(combined.outcomes) or [
            LogLine(
                hook_id=DISPATCHER_ID,
                rule_id="contract_fault",
                decision="degraded",
                effective="none",
                degraded=True,
            )
        ]
        self._log_unconfigured(ev, lines)
        return DispatchTrace(wire=wire, combined=combined, written=bool(results))

    def _log_hooks_off(self, payload: bytes) -> None:
        """``PLAYBOOK_HOOKS=off``: no output at all; one ``escape`` line per session."""
        from coding_agent_playbook.hook_runtime.harness._payload import decode_object, opt_str

        decoded = decode_object(payload, truncated=False)
        session_id = opt_str(decoded, "session_id") if isinstance(decoded, dict) else None
        line = LogLine(hook_id=DISPATCHER_ID, decision="escape", effective="none", escape=HOOKS_VAR)
        self._log_unconfigured(
            self._bare_event(session_id or ""), [line], once_key=f"escape:{HOOKS_VAR}"
        )

    def _bare_event(self, session_id: str) -> CanonicalEvent:
        return fault_event(
            self.event,
            self.harness,
            session_id=session_id,
            project_dir=self.root_guess,
            env=self.deps.env,
        )

    def _log_unconfigured(
        self, ev: CanonicalEvent, lines: list[LogLine], *, once_key: str | None = None
    ) -> None:
        """Lines decided before a config loaded are always logged: they mark an unguarded event."""
        repo = find_repo(self.root_guess)
        if repo is None or not ev.session_id:
            return
        store = self.deps.state or StateStore.for_repo(repo, clock=self.deps.clock)
        if once_key is not None and not SessionState(store, ev.session_id).once(once_key):
            return
        DecisionLog(store, ev, now=self.deps.clock.time, enabled=True, canary=self.canary).write(
            lines
        )
