"""Dangling-symlink predicates that never raise (``_symlinks.py``).

Regression (review of the dangling-link fix): ``is_symlink() and not exists()``
raised ``PermissionError`` for a link under an unreadable directory on Python
3.12/3.13, from inside sync's error handler, hiding the original error.
"""

from __future__ import annotations

import errno
import os
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._symlinks import is_dangling_symlink, unresolvable_link_errno

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


@pytest.fixture
def locked(tmp_path: Path) -> Iterator[Path]:
    """A directory nobody may search, restored afterwards so pytest can clean up."""
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    directory = tmp_path / "locked"
    (directory / "cc").mkdir(parents=True)
    directory.chmod(0)
    yield directory
    directory.chmod(0o755)


def test_a_missing_target_or_a_loop_is_unresolvable(tmp_path: Path) -> None:
    (tmp_path / "gone").symlink_to("missing", target_is_directory=True)
    (tmp_path / "loop").symlink_to("loop")

    assert unresolvable_link_errno(tmp_path / "gone") == errno.ENOENT
    assert unresolvable_link_errno(tmp_path / "loop") == errno.ELOOP
    assert is_dangling_symlink(tmp_path / "gone")
    assert is_dangling_symlink(tmp_path / "loop")


def test_a_live_link_or_a_non_link_is_not_dangling(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "live").symlink_to("real", target_is_directory=True)

    assert unresolvable_link_errno(tmp_path / "live") is None
    assert not is_dangling_symlink(tmp_path / "real")
    assert not is_dangling_symlink(tmp_path / "absent")


def test_a_link_into_an_unreadable_directory_is_not_called_dangling(
    tmp_path: Path, locked: Path
) -> None:
    (tmp_path / "into-locked").symlink_to(locked / "cc", target_is_directory=True)

    assert not is_dangling_symlink(tmp_path / "into-locked")  # EACCES: unknown, never raised
