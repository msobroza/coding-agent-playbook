"""Writes of generated output that refuse a FIFO, socket or device (``generated_output/output_io.py``).

Regression: ``mkfifo AGENTS.md`` made write-mode ``playbook sync`` hang forever
in ``open()``, and a socket there crashed it with ``OSError`` [Errno 102].
"""

from __future__ import annotations

import errno
import os
import socket
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.generated_output.output_io import (
    NotRegularFileError,
    copy_output,
    refuse_special_file,
    special_file_kind,
    write_output_bytes,
    write_output_text,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX FIFOs and sockets")


@pytest.fixture
def bound_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A unix socket at ``tmp_path / "s.md"`` (bound by a short relative name: AF_UNIX paths are capped)."""
    monkeypatch.chdir(tmp_path)
    sock = socket.socket(socket.AF_UNIX)
    sock.bind("s.md")
    yield tmp_path / "s.md"
    sock.close()


def test_a_fifo_is_refused_before_open(tmp_path: Path) -> None:
    fifo = tmp_path / "AGENTS.md"
    os.mkfifo(fifo)

    with pytest.raises(NotRegularFileError) as raised:
        write_output_text(fifo, "x\n")  # would block forever in open()

    assert raised.value.errno == errno.ENXIO
    assert raised.value.filename == str(fifo)
    assert special_file_kind(fifo) == "FIFO"


def test_a_socket_is_refused(bound_socket: Path) -> None:
    with pytest.raises(NotRegularFileError):
        write_output_bytes(bound_socket, b"x\n")
    assert special_file_kind(bound_socket) == "socket"


def test_a_link_to_a_fifo_is_refused_too(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "AGENTS.md").symlink_to("pipe")

    with pytest.raises(NotRegularFileError):
        write_output_text(tmp_path / "AGENTS.md", "x\n")


def test_regular_files_new_files_and_links_to_files_are_written_as_before(tmp_path: Path) -> None:
    (tmp_path / "old.md").write_text("old\n", encoding="utf-8")
    (tmp_path / "real.md").write_text("real\n", encoding="utf-8")
    (tmp_path / "link.md").symlink_to("real.md")

    write_output_text(tmp_path / "old.md", "new\n")
    write_output_bytes(tmp_path / "fresh.md", b"fresh\n")
    write_output_text(tmp_path / "link.md", "through\n")  # like Path.write_text: follows

    assert (tmp_path / "old.md").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "fresh.md").read_bytes() == b"fresh\n"
    assert (tmp_path / "real.md").read_text(encoding="utf-8") == "through\n"
    assert special_file_kind(tmp_path / "old.md") is None
    assert special_file_kind(tmp_path / "absent.md") is None


def test_a_directory_still_fails_the_write_as_before(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").mkdir()
    with pytest.raises(IsADirectoryError):
        write_output_text(tmp_path / "AGENTS.md", "x\n")
    assert special_file_kind(tmp_path / "AGENTS.md") is None


def test_refuse_special_file_is_the_guard_for_reads_too(tmp_path: Path) -> None:
    """Reading a FIFO blocks as well: ``.gitignore`` and ``settings.json`` are read first."""
    os.mkfifo(tmp_path / ".gitignore")
    with pytest.raises(NotRegularFileError):
        refuse_special_file(tmp_path / ".gitignore")
    refuse_special_file(tmp_path / "absent")  # nothing there: nothing to refuse


def test_a_character_device_is_written_as_before(tmp_path: Path) -> None:
    """``AGENTS.md -> /dev/null`` discards the output and never blocks: still allowed."""
    (tmp_path / "AGENTS.md").symlink_to(os.devnull)

    write_output_text(tmp_path / "AGENTS.md", "x\n")

    assert special_file_kind(tmp_path / "AGENTS.md") is None


def test_a_read_guard_refuses_a_character_device_too(tmp_path: Path) -> None:
    """``.claude/settings.json -> /dev/zero`` reads forever and ``/dev/tty`` blocks:
    the reads of ``.gitignore`` and ``settings.json`` refuse any device."""
    (tmp_path / "settings.json").symlink_to("/dev/zero")

    refuse_special_file(tmp_path / "settings.json")  # a write into it is fine
    with pytest.raises(NotRegularFileError):
        refuse_special_file(tmp_path / "settings.json", reading=True)
    assert special_file_kind(tmp_path / "settings.json", reading=True) == "character device"


def test_copy_output_writes_into_a_character_device_without_its_metadata(tmp_path: Path) -> None:
    """``copy2``'s copystat would chmod ``/dev/null`` and fail with EACCES: write the
    bytes only, like the other writers do."""
    src = tmp_path / "run.sh"
    src.write_bytes(b"echo hi\n")
    src.chmod(0o755)
    (tmp_path / "copy.sh").symlink_to(os.devnull)

    assert copy_output(src, tmp_path / "copy.sh") == tmp_path / "copy.sh"
    assert (tmp_path / "copy.sh").is_symlink()


def test_copy_output_refuses_a_directory_destination(tmp_path: Path) -> None:
    """Regression: ``shutil.copy2`` into a directory wrote ``dst/<name>`` and succeeded."""
    src = tmp_path / "run.sh"
    src.write_bytes(b"echo hi\n")
    (tmp_path / "dst.sh").mkdir()

    with pytest.raises(IsADirectoryError):
        copy_output(src, tmp_path / "dst.sh")

    assert list((tmp_path / "dst.sh").iterdir()) == []


def test_copy_output_refuses_a_fifo_destination_and_copies_otherwise(tmp_path: Path) -> None:
    src = tmp_path / "run.sh"
    src.write_bytes(b"echo hi\n")
    src.chmod(0o755)
    os.mkfifo(tmp_path / "pipe.sh")

    with pytest.raises(NotRegularFileError):
        copy_output(src, tmp_path / "pipe.sh")
    copied = copy_output(src, tmp_path / "copy.sh")

    assert copied == tmp_path / "copy.sh"
    assert copied.read_bytes() == b"echo hi\n"
    assert copied.stat().st_mode & 0o111  # copy2 keeps the mode
