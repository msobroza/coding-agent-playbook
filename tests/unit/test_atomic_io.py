"""The shared atomic byte writer (specs/prK-lifecycle-hooks.md §C.2.4 step 8)."""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._atomic_io import atomic_write_bytes
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.lockfile import Lockfile

if TYPE_CHECKING:
    from pathlib import Path

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


def test_writes_bytes_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    payload = b'\xef\xbb\xbf{\r\n  "a": 1\r\n}'
    atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_never_clobbers_a_user_tmp_file(tmp_path: Path) -> None:
    user_file = tmp_path / "settings.json.tmp"
    user_file.write_bytes(b"mine")
    atomic_write_bytes(tmp_path / "settings.json", b"{}")
    assert user_file.read_bytes() == b"mine"


@posix_only
def test_keeps_the_existing_mode(tmp_path: Path) -> None:
    target = tmp_path / "launch.sh"
    target.write_bytes(b"old")
    target.chmod(0o750)
    atomic_write_bytes(target, b"new")
    assert stat.S_IMODE(target.stat().st_mode) == 0o750


@posix_only
def test_new_file_gets_the_umask_default_not_0600(tmp_path: Path) -> None:
    umask = os.umask(0o022)
    try:
        atomic_write_bytes(tmp_path / "new.json", b"{}")
    finally:
        os.umask(umask)
    assert stat.S_IMODE((tmp_path / "new.json").stat().st_mode) == 0o644


def test_failed_replace_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "taken"
    target.mkdir()  # os.replace(file, directory) fails
    with pytest.raises(OSError):
        atomic_write_bytes(target, b"{}")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["taken"]


def test_state_source_saves_lockfile_through_the_byte_writer(tmp_path: Path) -> None:
    user_tmp = tmp_path / ".coding-agent-playbook.lock.tmp"
    user_tmp.write_bytes(b"user")
    state = FileSystemStateSource(repo_root=tmp_path)
    state.save_lockfile(Lockfile(2, "0.2.0", "2026-10-14T10:00:00Z"))

    data = (tmp_path / ".coding-agent-playbook.lock").read_bytes()
    assert b"\r\n" not in data
    assert data.startswith(b"schema_version = 2\n")
    assert user_tmp.read_bytes() == b"user"
