"""The Stop stage runner: pinned argv, signature check, one ``proc.run`` (specs/prK-lifecycle-hooks.md §D.5.2, §D.8.3).

A stage names a logical tool and its args; the absolute program comes from
the per-worktree ``machine.json`` pins, never from a repo file. A program
whose stat signature changed since sync is ``tool_changed``, a missing pin
``toolchain_missing`` with advice for the user, and every call goes through
``proc.run`` with a timeout (``FakeProc`` here: no real tool is needed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.pin import MachinePins, parse_machine_pins, tool_signature
from coding_agent_playbook.hook_runtime.stop.runner import PinnedStageRunner
from tests.hook_runtime.fakes import FakeProc

if TYPE_CHECKING:
    from pathlib import Path


def _pins(tool: Path, *, sig: list[int] | None = None) -> MachinePins:
    found = tool_signature(str(tool))
    assert found is not None
    entry = {"argv": [str(tool)], "sig": list(found) if sig is None else sig}
    pins = parse_machine_pins({"tools": {"ruff": entry}})
    assert pins is not None
    return pins


def _tool(tmp_path: Path) -> Path:
    path = tmp_path / "bin" / "ruff"
    path.parent.mkdir()
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    return path


def test_argv_is_machine_pin_plus_record_args(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    proc = FakeProc()
    proc.script([str(tool), "check"], stdout=b"[]", returncode=1)
    runner = PinnedStageRunner(proc, cwd=str(tmp_path), pins=lambda: _pins(tool))

    run = runner.run("ruff", ["check", "--output-format", "json", "."], timeout=2.5)

    assert (run.returncode, run.stdout, run.skip_category) == (1, b"[]", "")
    [call] = proc.calls
    assert call.argv == (str(tool), "check", "--output-format", "json", ".")
    assert (call.timeout, call.cwd) == (2.5, str(tmp_path))


def test_sig_mismatch_is_tool_changed(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    proc = FakeProc()
    runner = PinnedStageRunner(proc, cwd=str(tmp_path), pins=lambda: _pins(tool, sig=[1, 2, 3]))

    run = runner.run("ruff", ["check", "."], timeout=2.0)

    assert run.skip_category == "tool_changed"
    assert "ask the user to run playbook sync" in run.advice
    assert proc.calls == []
    result = run.skipped("lint")
    assert (result.status, result.skip_category, result.verified) == (
        "skipped",
        "tool_changed",
        False,
    )


def test_missing_machine_json_is_toolchain_missing_note(tmp_path: Path) -> None:
    proc = FakeProc()
    runner = PinnedStageRunner(proc, cwd=str(tmp_path), pins=lambda: None)

    no_pins = runner.run("ruff", ["check", "."], timeout=2.0)
    unpinned = PinnedStageRunner(proc, cwd=str(tmp_path), pins=lambda: _pins(_tool(tmp_path))).run(
        "mypy", [], timeout=2.0
    )

    assert no_pins.skip_category == unpinned.skip_category == "toolchain_missing"
    assert no_pins.advice.endswith("ask the user to run playbook sync in this worktree")
    assert unpinned.advice == "mypy not found on the pinned path; ask the user to run playbook sync"
    assert no_pins.skipped("lint").user_lines == (no_pins.advice,)
    assert proc.calls == []


def test_timeout_is_skipped_timeout(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    proc = FakeProc()
    proc.script([str(tool)], timeout=True)
    runner = PinnedStageRunner(proc, cwd=str(tmp_path), pins=lambda: _pins(tool))

    run = runner.run("ruff", ["check", "."], timeout=0.5)

    assert run.skip_category == "timeout"
    assert run.skipped("lint").skip_category == "timeout"
    assert [call.timeout for call in proc.calls] == [0.5]
