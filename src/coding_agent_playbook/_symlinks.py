"""Dangling-symlink predicates that never raise (stdlib only).

``is_symlink() and not exists()`` misjudges, and on Python 3.12/3.13 can
raise: ``Path.exists()`` raises on any error but ENOENT/ENOTDIR/EBADF/ELOOP,
so a live link under an unreadable directory (EACCES) either raised out of an
error handler or read as dangling. These ask ``os.stat`` and keep only the
errnos that mean the target is gone: missing, or a link loop.
"""

from __future__ import annotations

import errno
import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

#: Following the link fails because its target is missing or the links loop.
_UNRESOLVABLE: Final = frozenset({errno.ENOENT, errno.ENOTDIR, errno.ELOOP})


def unresolvable_link_errno(path: Path) -> int | None:
    """The errno following the symlink ``path`` fails with when its target is gone, else ``None``.

    ``ENOENT``/``ENOTDIR`` for a missing target, ``ELOOP`` for a link loop;
    ``None`` when ``path`` is no symlink, resolves, or cannot be judged (EACCES).

    Example: ``unresolvable_link_errno(repo / ".claude/commands")`` -> ``errno.ENOENT``
    for ``.claude/commands -> ../tools/cc`` with no ``tools/cc``.
    """
    if not os.path.islink(path):
        return None
    try:
        os.stat(path)
    except OSError as exc:
        return exc.errno if exc.errno in _UNRESOLVABLE else None
    return None


def is_dangling_symlink(path: Path) -> bool:
    """Whether ``path`` is a symlink whose target is missing or loops; never raises.

    Example: ``is_dangling_symlink(repo / ".claude/skills")`` after its target was removed -> ``True``.
    """
    return unresolvable_link_errno(path) is not None
