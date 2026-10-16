"""Atomic byte writes for files that may sit among user files (stdlib-only).

One implementation for every engine write that must never leave a
half-written file: the config, the lockfile, the managed ``.gitignore`` block
and ``.claude/settings.json`` (specs/prK-lifecycle-hooks.md §C.2.4 step 8).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

__all__ = ["atomic_write_bytes"]


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` through a unique temp file and ``os.replace``.

    A crash mid-write leaves either the old file or the new one, never a torn
    file. Bytes, not text mode, so no newline translation happens on Windows
    (``write_text`` would turn a CRLF-preserving merge into a rewrite). The temp
    name comes from :func:`tempfile.mkstemp` (``.<name>.<random>.tmp``), so a
    user's ``<name>.tmp`` is never clobbered, and the target's permission bits
    are carried over (a new file gets the umask default, not mkstemp's 0o600).

    Example::

        atomic_write_bytes(repo / ".claude" / "settings.json", b"{}\\n")
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        _copy_mode(target, tmp)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _copy_mode(target: Path, tmp: Path) -> None:
    """Give ``tmp`` the mode of ``target``, or the umask default when it is new."""
    if target.exists():
        shutil.copymode(target, tmp)
        return
    umask = os.umask(0)
    os.umask(umask)
    tmp.chmod(0o666 & ~umask)
