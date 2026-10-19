"""Writes of generated output that never open a FIFO, socket or block device (stdlib only).

``open()`` blocks on a FIFO until the other end appears, so ``mkfifo AGENTS.md``
hung ``playbook sync`` forever, and on a socket it fails with a raw errno (102
on macOS). Adapters and the sync-level hook outputs write each generated file
through these helpers, which first refuse a FIFO, a socket or a block device at
the path; a directory fails the write with ``IsADirectoryError`` (for
:func:`copy_output` too, where ``shutil.copy2`` would copy *into* it). The
refusal, :class:`NotRegularFileError`, is an ``OSError`` that ``playbook sync``
reports like any other blocker (``sync/_output_blockers.py``, SPEC §12.2).
:func:`refuse_special_file` guards the reads that come first, of ``.gitignore``
and ``.claude/settings.json``: reading a FIFO blocks too, and with ``reading``
a character device is refused there as well (``/dev/zero`` never ends). Like
``Path.write_text`` the helpers follow a symlink at the path, so a link to a FIFO
is refused as well; a character device is written into as before
(``AGENTS.md -> /dev/null`` discards the output and never blocks, and ``sync
--check`` counts it as delivered, :func:`is_character_device`).

The native skill writer needs none of this: it unlinks whatever sits at a
destination inside a claimed skill directory before writing (SPEC §10.8).
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path
from typing import Final

__all__ = [
    "NotRegularFileError",
    "copy_output",
    "is_character_device",
    "refuse_special_file",
    "special_file_kind",
    "write_output_bytes",
    "write_output_text",
]

#: The file types sync refuses to open, and the word its message uses for each.
_KINDS: Final = (
    (stat.S_ISFIFO, "FIFO"),
    (stat.S_ISSOCK, "socket"),
    (stat.S_ISBLK, "block device"),
)
#: What a read refuses as well: ``/dev/zero`` never ends, ``/dev/tty`` blocks.
_READ_KINDS: Final = (*_KINDS, (stat.S_ISCHR, "character device"))


class NotRegularFileError(OSError):
    """A FIFO, socket or block device sits where sync writes (or first reads) a file.

    Raised with ``errno.ENXIO`` (what a non-blocking ``open()`` of a FIFO with
    no reader reports) and the path as ``filename``.

    Example::

        NotRegularFileError(errno.ENXIO, "not a regular file (FIFO)", "AGENTS.md")
    """


def special_file_kind(path: Path, *, reading: bool = False) -> str | None:
    """``"FIFO"``, ``"socket"`` or ``"block device"`` at ``path`` (followed), else ``None``.

    ``None`` for a regular file, a directory, an absent or unreadable path, and
    a character device unless ``reading`` (then ``"character device"``). Never raises.

    Example: ``special_file_kind(repo / "AGENTS.md")`` -> ``"FIFO"`` after ``mkfifo AGENTS.md``.
    """
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return None
    kinds = _READ_KINDS if reading else _KINDS
    return next((kind for test, kind in kinds if test(mode)), None)


def is_character_device(path: Path) -> bool:
    """Whether ``path`` (followed) is a character device such as ``/dev/null``. Never raises.

    Example: ``is_character_device(repo / "AGENTS.md")`` -> ``True`` for ``AGENTS.md -> /dev/null``.
    """
    return special_file_kind(path, reading=True) == "character device"


def write_output_text(path: Path, text: str) -> None:
    """``path.write_text(text, encoding="utf-8")``, refusing a FIFO, socket or block device there.

    Example: ``write_output_text(repo / "AGENTS.md", content)``.
    """
    refuse_special_file(path)
    path.write_text(text, encoding="utf-8")


def write_output_bytes(path: Path, data: bytes) -> None:
    """``path.write_bytes(data)``, refusing a FIFO, socket or block device there.

    Example: ``write_output_bytes(out / GUARD_CONFIG_REL, serialized)``.
    """
    refuse_special_file(path)
    path.write_bytes(data)


def copy_output(src: Path, dst: Path) -> Path:
    """``shutil.copy2(src, dst)`` (bytes and mode) to the file ``dst``; refuses a special file there.

    A directory at ``dst`` raises ``IsADirectoryError`` like the other writers:
    ``copy2`` itself would copy into it and succeed, dropping the generated file
    inside the user's directory. Into a character device (``-> /dev/null``) only
    the bytes go, as with the other writers: ``copy2``'s copystat would chmod the
    device and fail with EACCES.

    Example: ``copy_output(handler_script, out / ".coding-agent-playbook/hooks/scripts/x/run.sh")``.
    """
    refuse_special_file(dst)
    if os.path.isdir(dst):
        raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(dst))
    if is_character_device(dst):
        dst.write_bytes(src.read_bytes())
        return dst
    return Path(shutil.copy2(src, dst))


def refuse_special_file(path: Path, *, reading: bool = False) -> None:
    """Raise :class:`NotRegularFileError` when ``path`` holds a FIFO, socket or block device.

    With ``reading`` a character device is refused too: sync reads ``.gitignore``
    and ``.claude/settings.json`` before replacing them.

    Example: ``refuse_special_file(repo / ".gitignore", reading=True)`` before reading it.
    """
    kind = special_file_kind(path, reading=reading)
    if kind is not None:
        raise NotRegularFileError(errno.ENXIO, f"not a regular file ({kind})", str(path))
