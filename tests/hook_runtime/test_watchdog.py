"""The event watchdog and the single output write (specs/prK-lifecycle-hooks.md §D.4).

In-process, the timer is a ``FakeTimer`` fired by the test (here: from inside
a handler, as a hung handler would see the deadline pass) and ``exit`` raises
``FakeExit``. One subprocess smoke test runs the real thread and ``os._exit``.
"""

from __future__ import annotations

import io
import json
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch import run_event
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.harness.wire import DENY_EXIT, WireOutput
from coding_agent_playbook.hook_runtime.registry import HANDLER_ATTR, HandlerDeclaration
from coding_agent_playbook.hook_runtime.watchdog import OutputGate, Watchdog
from tests.hook_runtime.fakes import FakeExit, FakeHandlerResolver, FakeTimers, fake_exit
from tests.hook_runtime.guard_repo import GuardRepo, hook_record, streams
from tests.import_probe import probe_env

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.proc import SubprocessProc
    from coding_agent_playbook.hook_runtime.registry import HandlerContext, HandlerFn

PRE = EventName.PRE_TOOL_USE


def _context(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
    return HandlerResult(decision=Decision.CONTEXT, hook_id=ctx.hook.id, context=("kept",))


def _setup(
    tmp_path: Path,
    runtime_deps: Callable[..., RuntimeDeps],
    *,
    failure_reason: str | None = None,
    **env: str,
) -> tuple[GuardRepo, RuntimeDeps, FakeTimers]:
    """guard-a gives context, then guard-b hangs past the deadline.

    ``failure_reason`` is declared on guard-b's handler, as ``register_hook_handler`` would.
    """
    repo = GuardRepo.create(tmp_path)
    repo.install(
        hook_record("guard-a", priority=1),
        hook_record("guard-b", priority=2),
        deadlines_ms={"pre_tool_use": 1500},
    )
    timers = FakeTimers()

    def hangs(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
        timers.made[0].fire()  # the deadline passes while this handler runs
        raise AssertionError("unreachable: the watchdog ended the process")

    if failure_reason is not None:
        setattr(hangs, HANDLER_ATTR, _declaration(hangs, failure_reason))
    out, err = streams()
    deps = runtime_deps(
        env=repo.env(**env),
        out=out,
        err=err,
        timer_factory=timers,
        exit=fake_exit,
        resolve_handler=FakeHandlerResolver({"guard-a": _context, "guard-b": hangs}),
    )
    return repo, deps, timers


def _declaration(fn: HandlerFn, reason: str) -> HandlerDeclaration:
    return HandlerDeclaration(
        name="guard_b",
        module=__name__,
        events=frozenset({PRE}),
        decisions=frozenset({Decision.ASK}),
        config_schema={},
        failure_reason=reason,
        fn=fn,
    )


def test_watchdog_writes_decided_output_exactly_once(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, deps, timers = _setup(tmp_path, runtime_deps)

    with pytest.raises(FakeExit) as exited:
        run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    out = deps.out.getvalue()  # type: ignore[union-attr]
    body = json.loads(out)  # exactly one JSON document
    assert body["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "Playbook guard guard-b failed internally" in out
    assert exited.value.code == 0
    assert timers.made[0].interval == pytest.approx(1.5)
    (line,) = repo.decisions()
    assert (line["hook_id"], line["rule_id"], line["decision"]) == (
        "guard-b",
        "watchdog",
        "degraded",
    )


def test_watchdog_shows_a_running_guards_declared_failure_reason(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    """A guard that declared ``failure_reason`` keeps it when the deadline cuts it off."""
    repo, deps, _ = _setup(tmp_path, runtime_deps, failure_reason="Guard B timed out; retry.")

    with pytest.raises(FakeExit):
        run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    assert isinstance(deps.out, io.StringIO)
    specific = json.loads(deps.out.getvalue())["hookSpecificOutput"]
    assert specific["permissionDecisionReason"] == "Guard B timed out; retry."


def test_watchdog_denies_unattended_with_the_deny_exit(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, deps, _ = _setup(tmp_path, runtime_deps, CI="true")

    with pytest.raises(FakeExit) as exited:
        run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    assert exited.value.code == DENY_EXIT
    assert deps.err.getvalue().startswith("Needs user confirmation")  # type: ignore[union-attr]


def test_main_path_write_wins_and_watchdog_is_noop() -> None:
    out, err = streams()
    gate = OutputGate(out, err)
    exits: list[int] = []

    class Deps:
        def timer_factory(self, interval: float, function: Callable[[], None]) -> None:
            raise AssertionError("not armed in this test")

        def exit(self, code: int) -> None:
            exits.append(code)

    dog = Watchdog(Deps(), gate, fallback=lambda: WireOutput("late\n", "", 10))  # type: ignore[arg-type]

    assert gate.write(WireOutput("main\n")) is True
    dog.fire()

    assert (out.getvalue(), exits) == ("main\n", [])
    assert gate.write(WireOutput("again\n")) is False


def test_timer_is_cancelled_after_the_main_write(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = GuardRepo.create(tmp_path)
    repo.install(hook_record("guard-a"))
    timers = FakeTimers()
    deps = runtime_deps(
        env=repo.env(),
        timer_factory=timers,
        exit=fake_exit,
        resolve_handler=FakeHandlerResolver({"guard-a": _context}),
    )

    run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    (timer,) = timers.made
    assert (timer.started, timer.cancelled) == (True, True)


def test_no_timer_when_no_hook_is_selected(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = GuardRepo.create(tmp_path)
    repo.install()
    timers = FakeTimers()

    run_event(
        PRE,
        Harness.CLAUDE_CODE,
        repo.payload(PRE, tool="Bash"),
        runtime_deps(env=repo.env(), timer_factory=timers, exit=fake_exit),
    )

    assert timers.made == []


_SMOKE = """
import sys, time
from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.harness.wire import WireOutput
from coding_agent_playbook.hook_runtime.watchdog import OutputGate, Watchdog

deps = RuntimeDeps.default()
gate = OutputGate(sys.stdout, sys.stderr)
Watchdog(deps, gate, fallback=lambda: WireOutput('{"decided":true}\\n', "", 10)).arm(0.05)
time.sleep(30)
print("main path never finishes")
"""


def test_real_os_exit_smoke(real_proc: SubprocessProc) -> None:
    result = real_proc.run([sys.executable, "-I", "-c", _SMOKE], timeout=20, env=probe_env())

    assert (result.returncode, result.stdout) == (10, b'{"decided":true}\n')


def test_gate_survives_a_closed_stream() -> None:
    out, err = streams()
    out.close()
    gate = OutputGate(out, err)

    assert gate.write(WireOutput("x\n", "why\n")) is True
    assert gate.written == WireOutput("x\n", "why\n")
    assert err.getvalue() == "why\n"
    gate.note("late note")
    assert err.getvalue() == "why\nlate note\n"
