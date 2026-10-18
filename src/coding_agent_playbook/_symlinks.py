"""Symlink predicates and resolution that never raise (stdlib only).

``is_symlink() and not exists()`` misjudges, and on Python 3.12/3.13 can
raise: ``Path.exists()`` raises on any error but ENOENT/ENOTDIR/EBADF/ELOOP,
so a live link under an unreadable directory (EACCES) either raised out of an
error handler or read as dangling. These ask ``os.stat`` and keep only the
errnos that mean the target is gone: missing, or a link loop.

:func:`real_path` stands in for ``Path.resolve()`` on paths a user's link can
make loop: on Python 3.12 ``resolve()`` raises ``RuntimeError`` on a symlink
loop (3.13 does not, and CI runs both), so ``.claude/commands -> commands``
crashed ``playbook sync`` there before any message.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Final

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


def real_path(path: Path) -> Path:
    """``Path(os.path.realpath(path))``: ``Path.resolve()`` (non-strict) that never raises.

    A link loop is left unresolved, like a missing target, where Python 3.12's
    ``resolve()`` raises ``RuntimeError``.

    Example: ``real_path(repo / ".claude/commands")`` -> the path itself for
    ``.claude/commands -> commands``.
    """
    return Path(os.path.realpath(path))


def link_leaving(directory: Path, root: Path) -> Path | None:
    """The first symlink from ``root`` down to ``directory`` that leads outside ``root``.

    ``None`` when every link on the way stays inside. A dangling link counts by
    where it points. The skill writer skips a file under such a link inside a
    skill directory, and ``sync --check`` names the link (SPEC §10.8, §12.3).

    Example: ``link_leaving(skill_dir / "scripts" / "deep", skill_dir)`` ->
    ``skill_dir / "scripts"`` for ``scripts -> /elsewhere``.
    """
    inside = real_path(root)
    current = root
    for part in directory.relative_to(root).parts:
        current = current / part
        if current.is_symlink() and not real_path(current).is_relative_to(inside):
            return current
    return None


def is_dangling_symlink(path: Path) -> bool:
    """Whether ``path`` is a symlink whose target is missing or loops; never raises.

    Example: ``is_dangling_symlink(repo / ".claude/skills")`` after its target was removed -> ``True``.
    """
    return unresolvable_link_errno(path) is not None
