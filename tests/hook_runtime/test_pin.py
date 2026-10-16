"""The interpreter pin and the per-machine tool pins (specs/prK-lifecycle-hooks.md §C.2.7, §D.8.3).

Both live in the per-worktree state root, never in a committed file: the
committed launcher is machine-independent and reads the interpreter from
``<git_dir>/playbook-hooks/interpreter``; ``machine.json`` holds absolute tool
paths with ``[size, mtime_ns, ino]`` signatures so a changed tool is never
reported green.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from coding_agent_playbook.hook_runtime.pin import (
    INTERPRETER_PIN,
    MACHINE_PINS,
    ensure_interpreter_pin,
    is_ephemeral,
    read_interpreter_pin,
    read_machine_pins,
    tool_signature,
    write_machine_pins,
)
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME


def _git_dir(tmp_path: Path) -> Path:
    git_dir = Path(os.path.realpath(tmp_path)) / "repo" / ".git"
    git_dir.mkdir(parents=True)
    return git_dir


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_pin_is_unresolved_sys_executable_mode_0600(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    real = _executable(tmp_path / "toolchain" / "python3.13")
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(real)  # a venv's bin/python is a symlink: never resolve it

    result = ensure_interpreter_pin(git_dir=str(git_dir), executable=str(venv_python))

    assert result is not None and result.written
    pin = git_dir / STATE_DIR_NAME / INTERPRETER_PIN
    assert result.path == pin
    assert pin.read_text(encoding="utf-8") == f"{venv_python}\n"
    assert stat.S_IMODE(pin.stat().st_mode) == 0o600
    assert stat.S_IMODE((git_dir / STATE_DIR_NAME).stat().st_mode) == 0o700
    assert read_interpreter_pin(git_dir=str(git_dir)) == str(venv_python)


def test_first_writer_wins_unless_pin_not_executable(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    first = _executable(tmp_path / "a" / "python")
    second = _executable(tmp_path / "b" / "python")

    ensure_interpreter_pin(git_dir=str(git_dir), executable=str(first))
    kept = ensure_interpreter_pin(git_dir=str(git_dir), executable=str(second))
    assert kept is not None and not kept.written and kept.interpreter == str(first)

    first.chmod(0o644)  # the pinned interpreter stopped being executable
    replaced = ensure_interpreter_pin(git_dir=str(git_dir), executable=str(second))
    assert replaced is not None and replaced.written
    assert read_interpreter_pin(git_dir=str(git_dir)) == str(second)

    forced = ensure_interpreter_pin(git_dir=str(git_dir), executable=str(first), force=True)
    assert forced is not None and forced.written  # doctor --repin
    assert read_interpreter_pin(git_dir=str(git_dir)) == str(first)


@pytest.mark.parametrize(
    ("executable", "ephemeral"),
    [
        ("/home/u/.cache/uv/archive-v0/AbC123/bin/python", True),
        ("/Users/u/Library/Caches/uv/archive-v0/x/bin/python3", True),
        ("/home/u/.local/pipx/.cache/0f1e2d/bin/python", True),
        ("/home/u/project/.venv/bin/python", False),
        ("/usr/bin/python3", False),
    ],
)
def test_ephemeral_interpreter_is_reported(
    tmp_path: Path, executable: str, ephemeral: bool
) -> None:
    git_dir = _git_dir(tmp_path)

    result = ensure_interpreter_pin(git_dir=str(git_dir), executable=executable)

    assert is_ephemeral(executable) is ephemeral
    assert result is not None and result.ephemeral is ephemeral


def test_no_pin_outside_git(tmp_path: Path) -> None:
    plain = Path(os.path.realpath(tmp_path)) / "not-a-repo"
    plain.mkdir()

    assert ensure_interpreter_pin(start=str(plain), executable="/usr/bin/python3") is None
    assert read_interpreter_pin(start=str(plain)) is None
    assert write_machine_pins(start=str(plain), tools={}, engine_version="0") is None
    assert read_machine_pins(start=str(plain)) is None
    assert list(plain.iterdir()) == []


def test_pin_helpers_find_the_git_dir_from_start(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    nested = git_dir.parent / "src"
    nested.mkdir()

    ensure_interpreter_pin(start=str(nested), executable="/usr/bin/python3")

    assert read_interpreter_pin(git_dir=str(git_dir)) == "/usr/bin/python3"


def test_unusable_state_root_writes_no_pin(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (git_dir / STATE_DIR_NAME).symlink_to(elsewhere)

    assert ensure_interpreter_pin(git_dir=str(git_dir), executable="/usr/bin/python3") is None
    assert read_interpreter_pin(git_dir=str(git_dir)) is None
    assert list(elsewhere.iterdir()) == []


def test_machine_pins_record_size_mtime_ino_signature(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    ruff = _executable(tmp_path / "venv" / "bin" / "ruff")
    info = os.stat(ruff)

    path = write_machine_pins(
        git_dir=str(git_dir),
        tools={"ruff": [str(ruff), "--quiet"], "cz": ["/no/such/cz"]},
        resource_roots={"pkg:coding_agent_playbook/resources": "/site/resources"},
        engine_version="0.1.0a0",
    )

    assert path == git_dir / STATE_DIR_NAME / MACHINE_PINS
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    pins = read_machine_pins(git_dir=str(git_dir))
    assert pins is not None
    assert pins.engine_version == "0.1.0a0"
    assert pins.resource_roots == {"pkg:coding_agent_playbook/resources": "/site/resources"}
    pinned = pins.tool("ruff")
    assert pinned is not None
    assert pinned.argv == (str(ruff), "--quiet")
    assert pinned.sig == (info.st_size, info.st_mtime_ns, info.st_ino) == tool_signature(str(ruff))
    assert pinned.unchanged()
    missing = pins.tool("cz")
    assert missing is not None and missing.sig is None and not missing.unchanged()
    assert pins.tool("mypy") is None

    ruff.write_text("#!/bin/sh\necho upgraded\n", encoding="utf-8")
    assert not pinned.unchanged()  # a changed tool is skipped, never green


def test_ruff_drop_list_round_trips_sorted_and_only_when_set(tmp_path: Path) -> None:
    """``tools.ruff.drop``: the codes the pinned ruff cannot run (specs/prK-hook-pack.md §E.3)."""
    git_dir = _git_dir(tmp_path)
    ruff = _executable(tmp_path / "venv" / "bin" / "ruff")

    write_machine_pins(
        git_dir=str(git_dir),
        tools={"ruff": [str(ruff)], "cz": ["/no/such/cz"]},
        drops={"ruff": ["UP045", "DOC201", "UP045"]},
        engine_version="0",
    )

    document = json.loads((git_dir / STATE_DIR_NAME / MACHINE_PINS).read_text(encoding="utf-8"))
    assert document["tools"]["ruff"]["drop"] == ["DOC201", "UP045"]
    assert "drop" not in document["tools"]["cz"]
    pins = read_machine_pins(git_dir=str(git_dir))
    assert pins is not None
    assert pins.tools["ruff"].drop == {"DOC201", "UP045"}
    assert pins.tools["cz"].drop == frozenset()


def test_malformed_drop_list_reads_as_absent(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    write_machine_pins(git_dir=str(git_dir), tools={}, engine_version="0")
    bad = {"tools": {"ruff": {"argv": ["/v/ruff"], "sig": None, "drop": "UP045"}}}
    (git_dir / STATE_DIR_NAME / MACHINE_PINS).write_text(json.dumps(bad), encoding="utf-8")

    assert read_machine_pins(git_dir=str(git_dir)) is None


def test_corrupt_machine_pins_read_as_absent(tmp_path: Path) -> None:
    git_dir = _git_dir(tmp_path)
    write_machine_pins(git_dir=str(git_dir), tools={}, engine_version="0")
    (git_dir / STATE_DIR_NAME / MACHINE_PINS).write_text('{"tools": 3}', encoding="utf-8")

    assert read_machine_pins(git_dir=str(git_dir)) is None
