"""The process seam and the injectable runtime dependencies (specs/prK-lifecycle-hooks.md §D.1, §D.9).

``proc`` is the runtime's only way to start a process: these tests prove it
imports ``subprocess`` lazily, insists on a timeout, never hands the hook's
stdin to a child, and turns a timeout into the runtime's own ``ProcTimeout``.
The rows that spawn a real interpreter request the plain ``real_proc`` fixture;
everything else runs on ``FakeProc``.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps, SystemClock, thread_timer
from coding_agent_playbook.hook_runtime.dispatch.proc import (
    ProcResult,
    ProcTimeout,
    SubprocessProc,
    run,
    which,
)
from tests.hook_runtime.fakes import FakeClock, FakeProc, FakeTrustStore
from tests.import_probe import new_modules_after, probe_env

if TYPE_CHECKING:
    from collections.abc import Callable


def test_proc_module_imports_no_subprocess_until_used() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hook_runtime.dispatch.proc")

    assert "subprocess" not in loaded
    assert "shutil" not in loaded


def test_deps_module_imports_no_thread_or_process_machinery() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hook_runtime.dispatch.deps")

    assert not {"subprocess", "shutil", "threading"} & set(loaded)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_run_requires_a_positive_finite_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        run(["true"], timeout=timeout)


def test_run_rejects_an_empty_argv() -> None:
    with pytest.raises(ValueError, match="argv"):
        run([], timeout=1)


def test_run_captures_output_and_feeds_input(real_proc: SubprocessProc) -> None:
    code = "import sys; data = sys.stdin.read(); print(data.upper()); sys.exit(3)"

    result = real_proc.run(
        [sys.executable, "-I", "-c", code], timeout=60, input=b"hi", env=probe_env()
    )

    assert result == ProcResult(
        argv=(sys.executable, "-I", "-c", code), returncode=3, stdout=b"HI\n", stderr=b""
    )
    assert not result.ok


def test_run_never_inherits_the_hook_stdin(real_proc: SubprocessProc) -> None:
    code = "import sys; print(repr(sys.stdin.read()))"

    result = real_proc.run([sys.executable, "-I", "-c", code], timeout=60, env=probe_env())

    assert result.ok
    assert result.stdout == b"''\n"


def test_run_timeout_raises_proc_timeout_naming_the_program(real_proc: SubprocessProc) -> None:
    with pytest.raises(ProcTimeout) as caught:
        real_proc.run([sys.executable, "-I", "-c", "import time; time.sleep(30)"], timeout=0.2)

    assert caught.value.program == sys.executable
    assert caught.value.timeout == 0.2
    assert "0.2" in str(caught.value)


def test_run_uses_the_given_cwd_and_env(
    real_proc: SubprocessProc, tmp_path: os.PathLike[str]
) -> None:
    code = "import os; print(os.getcwd()); print(os.environ.get('PROBE_X'))"
    env = {**probe_env(), "PROBE_X": "42"}

    result = real_proc.run(
        [sys.executable, "-I", "-c", code], timeout=60, env=env, cwd=str(tmp_path)
    )

    cwd, value = result.stdout.decode().splitlines()
    assert os.path.realpath(cwd) == os.path.realpath(tmp_path)
    assert value == "42"


def test_which_finds_a_program_on_the_given_path(tmp_path: os.PathLike[str]) -> None:
    tool = os.path.join(tmp_path, "tool")
    with open(tool, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\n")
    os.chmod(tool, 0o755)

    assert which("tool", path=str(tmp_path)) == tool
    assert which("absent-tool", path=str(tmp_path)) is None
    assert SubprocessProc().which("tool", path=str(tmp_path)) == tool


def test_fake_proc_rejects_an_unscripted_call() -> None:
    proc = FakeProc()

    with pytest.raises(AssertionError, match="unexpected subprocess: git"):
        proc.run(["git", "status"], timeout=1)


def test_fake_proc_replays_scripted_results_and_records_calls() -> None:
    proc = FakeProc()
    proc.script(["git", "--version"], stdout=b"git version 2.39.3\n")
    proc.script(["git", "status"], timeout=True)

    assert proc.run(["git", "--version"], timeout=2).stdout == b"git version 2.39.3\n"
    with pytest.raises(ProcTimeout):
        proc.run(["git", "status"], timeout=2)
    assert [call.argv for call in proc.calls] == [("git", "--version"), ("git", "status")]
    assert proc.calls[0].timeout == 2


def test_runtime_deps_defaults_are_real_and_isolated() -> None:
    deps = RuntimeDeps()

    assert isinstance(deps.proc, SubprocessProc)
    assert isinstance(deps.clock, SystemClock)
    assert deps.git is None and deps.state is None and deps.trust is None
    assert deps.exit is os._exit
    assert deps.env == dict(os.environ)
    assert deps.env is not os.environ  # a snapshot: later edits never leak in


def test_runtime_deps_fixture_hands_out_fakes(runtime_deps: Callable[..., RuntimeDeps]) -> None:
    deps = runtime_deps(env={"CI": "true"})

    assert isinstance(deps.proc, FakeProc)
    assert isinstance(deps.clock, FakeClock)
    assert isinstance(deps.trust, FakeTrustStore)
    assert deps.env == {"CI": "true"}


def test_system_clock_reads_both_clocks() -> None:
    clock = SystemClock()

    assert clock.monotonic() <= clock.monotonic()
    assert clock.time() > 1_700_000_000


def test_thread_timer_is_a_daemon_that_can_be_cancelled() -> None:
    fired: list[bool] = []
    timer = thread_timer(60.0, lambda: fired.append(True))

    timer.start()
    timer.cancel()
    timer.join(timeout=5)

    assert timer.daemon
    assert fired == []
