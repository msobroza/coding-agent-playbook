"""Symlink predicates and resolution that never raise (stdlib only).

``is_symlink() and not exists()`` misjudges, and on Python 3.12/3.13 can
raise: ``Path.exists()`` raises on any error but ENOENT/ENOTDIR/EBADF/ELOOP,
so a live link under an unreadable directory (EACCES) either raised out of an
error handler or read as dangling. These ask ``os.stat`` and keep only the
errnos that mean the target is gone: missing, or a link loop.

:func:`real_path` stands in for ``Path.resolve()`` on paths a user's link can
make loop: on Python 3.12 ``resolve()`` raises ``RuntimeError`` on a symlink
loop (3.13 does not, and CI runs both), so ``.claude/commands -> commands``
crashed ``playbook sync`` there before any message. :class:`BatchRealPaths` is
:func:`real_path` for the many paths of one read-only batch.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

#: Following the link fails because its target is missing or the links loop.
_UNRESOLVABLE: Final = frozenset({errno.ENOENT, errno.ENOTDIR, errno.ELOOP})

#: ``os.path.realpath`` walks ``/``-separated names (posixpath), which
#: :class:`BatchRealPaths` relies on; elsewhere it only delegates.
_POSIX_PATHS: Final = os.name == "posix"

#: Last names ``realpath(parent)/name`` does not hold for: the root's ``""``, and
#: ``..``, which steps out of the *resolved* parent (``Path`` drops ``.``).
_NOT_PLAIN_NAMES: Final = frozenset({"", ".", ".."})


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


class BatchRealPaths:
    """:func:`real_path` for the paths of one read-only batch, each directory resolved once.

    ``os.path.realpath`` lstats every component of every path, so the siblings
    of a deep tree pay for their shared parents again and again (one sync:
    132,662 lstat calls from 10,351 realpaths). Here every spelling resolved is
    memoized, and a path whose parent is known costs one lstat proving its last
    name is no symlink: its real path is then ``real(parent)/name``, the string
    ``realpath`` builds. A symlinked last name, a ``..`` or root name, a relative
    path, or a non-POSIX ``os.path`` falls back to ``os.path.realpath``, so
    ``real(p) == real_path(p)`` for every ``p``, dangling links and loops included.

    The memo is filesystem state: make one per batch computation that writes
    nothing between its lookups; never keep one across a write, never module-level.

    Example::

        real = BatchRealPaths()
        resolved = {real.real(path) for path in written}  # == {real_path(p) for p in written}
    """

    def __init__(self, *, lstat: Callable[[str], os.stat_result] = os.lstat) -> None:
        self._lstat = lstat
        self._known: dict[str, str] = {}

    def real(self, path: Path) -> Path:
        """``real_path(path)``, reusing what this batch already resolved."""
        spelled = os.fspath(path)
        if not (_POSIX_PATHS and spelled.startswith("/")):
            return Path(os.path.realpath(spelled))  # relative: realpath reads the cwd
        return Path(self._resolve(spelled))

    def _resolve(self, spelled: str) -> str:
        """The real path of absolute ``spelled``: up to a known ancestor, then down by name."""
        pending: list[str] = []
        current = spelled
        while current not in self._known and _last_name(current) not in _NOT_PLAIN_NAMES:
            pending.append(current)
            current = current.rpartition("/")[0] or "/"
        known = self._known.get(current)
        if known is None:  # the root, or a ``..`` name
            known = self._known[current] = os.path.realpath(current)
        for child in reversed(pending):
            known = self._known[child] = self._child(known, child)
        return known

    def _child(self, real_parent: str, spelled: str) -> str:
        """``real_parent/name`` for ``spelled``'s last name, unless that name is a link."""
        name = _last_name(spelled)
        candidate = real_parent + name if real_parent.endswith("/") else f"{real_parent}/{name}"
        if self._may_be_link(candidate):
            return os.path.realpath(spelled)
        return candidate

    def _may_be_link(self, candidate: str) -> bool:
        """Whether ``candidate`` is a symlink, judged as ``realpath``'s own lstat judges it.

        A failed lstat (missing, ENOTDIR, ELOOP, EACCES) is no link to ``realpath``
        either; a ``ValueError`` (an embedded NUL) proves nothing, so it falls back.
        """
        try:
            return stat.S_ISLNK(self._lstat(candidate).st_mode)
        except OSError:
            return False
        except ValueError:
            return True


def _last_name(spelled: str) -> str:
    """The name after the last ``/`` (``""`` for the root)."""
    return spelled.rpartition("/")[2]


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
