"""File primitives of the state root: private dirs, no-follow reads, atomic writes (§D.6.1).

Split from ``store.py`` to keep both under §D.1's 300-line module rule. Every
helper refuses to follow a symlink, because the agent runs as the same user
and could plant one to redirect state onto a file of its choosing.
"""

from __future__ import annotations

import errno
import json
import os
import stat
import sys
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = [
    "DIR_MODE",
    "FILE_MODE",
    "FOREIGN_BITS",
    "MAX_DOCUMENT_BYTES",
    "STATE_VERSION",
    "StateUnavailable",
    "as_document",
    "encode",
    "ensure_private_dir",
    "lstat_or_create",
    "ownership_problem",
    "parts",
    "read_regular",
    "root_problem",
    "write_new",
    "write_version",
]

#: Written to ``VERSION`` once, so a future layout change can be detected.
STATE_VERSION: Final = "1"
DIR_MODE: Final = 0o700
FILE_MODE: Final = 0o600
#: A state document larger than this is treated as corrupt (read as empty).
MAX_DOCUMENT_BYTES: Final = 16 * 1024 * 1024

_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS: Final = os.O_RDONLY | _NOFOLLOW | getattr(os, "O_BINARY", 0)
_NEW_FILE_FLAGS: Final = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | getattr(os, "O_BINARY", 0)
)
FOREIGN_BITS: Final = 0o077


class StateUnavailable(Exception):
    """This state operation cannot run; the caller proceeds stateless (§D.4).

    Example::

        >>> str(StateUnavailable("state root is a symlink"))
        'state root is a symlink'
    """


def parts(rel: str) -> list[str]:
    """The components of ``rel``; ``ValueError`` for a path that could leave the root.

    Example::

        >>> parts("sessions/ab/session.json")
        ['sessions', 'ab', 'session.json']
    """
    parts = rel.split("/")
    if not rel or rel.startswith("/") or any(p in ("", ".", "..") or "\\" in p for p in parts):
        raise ValueError(f"state path {rel!r} must be a relative '/'-separated path below the root")
    return parts


def root_problem(root: Path, uid: int | None) -> str | None:
    """Why ``root`` cannot hold private state (``None``: it can), creating it 0700 if absent.

    A permissive mode is tightened; a symlink, a non-directory, a root owned by
    another user than ``uid`` (default: this process's) or an unwritable one is
    refused, and the store runs stateless.

    Example::

        >>> root_problem(Path("/proc/1"), None)  # doctest: +SKIP
        'state root is owned by uid 0, not 501'
    """
    try:
        info = lstat_or_create(root)
    except OSError as exc:
        return f"cannot create state root {str(root)!r}: {exc.strerror}"
    problem = ownership_problem(info, uid)
    if problem is not None:
        return problem
    try:
        if stat.S_IMODE(info.st_mode) & FOREIGN_BITS:
            os.chmod(root, DIR_MODE)
        if not os.access(root, os.W_OK | os.X_OK):
            return "state root is not writable"
        write_version(root)
    except OSError as exc:
        return f"state root unusable: {exc.strerror}"
    return None


def lstat_or_create(directory: Path) -> os.stat_result:
    try:
        return os.lstat(directory)
    except FileNotFoundError:
        try:
            os.mkdir(directory, DIR_MODE)
            os.chmod(directory, DIR_MODE)  # mkdir's mode is masked by the umask
        except FileExistsError:
            pass  # a concurrent hook created it first
        return os.lstat(directory)


def ownership_problem(info: os.stat_result, uid: int | None) -> str | None:
    if stat.S_ISLNK(info.st_mode):
        return "state root is a symlink; refusing to follow it"
    if not stat.S_ISDIR(info.st_mode):
        return "state root is not a directory"
    if sys.platform == "win32":  # pragma: no cover - CI is POSIX-only (Q-D6)
        return None
    expected = os.getuid() if uid is None else uid
    if info.st_uid != expected:
        return f"state root is owned by uid {info.st_uid}, not {expected}"
    return None


def ensure_private_dir(directory: Path) -> None:
    try:
        info = lstat_or_create(directory)
    except OSError as exc:
        raise StateUnavailable(f"cannot create {directory.name!r}: {exc.strerror}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise StateUnavailable(f"state path {directory.name!r} is a symlink; refusing to follow it")
    if not stat.S_ISDIR(info.st_mode):
        raise StateUnavailable(f"state path {directory.name!r} is not a directory")


def write_version(root: Path) -> None:
    with suppress(FileExistsError):  # written once, by whichever hook got there first
        write_new(root / "VERSION", f"{STATE_VERSION}\n".encode("ascii"))


def write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, _NEW_FILE_FLAGS, FILE_MODE)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
    finally:
        os.close(descriptor)


def read_regular(path: Path, limit: int) -> bytes | None:
    """The bytes of a regular, non-symlinked file, or ``None`` when absent or over ``limit``."""
    try:
        descriptor = os.open(path, _READ_FLAGS)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise StateUnavailable(f"state file {path.name!r} is a symlink") from exc
        raise StateUnavailable(f"cannot read state file {path.name!r}: {exc.strerror}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise StateUnavailable(f"state file {path.name!r} is not a regular file")
        data = handle.read(limit + 1)
    return None if len(data) > limit else data


def as_document(data: bytes | None) -> dict[str, Any]:
    if data is None:
        return {}
    try:
        document = json.loads(data)
    except ValueError:
        return {}  # corrupt: the next write replaces it
    return document if isinstance(document, dict) else {}


def encode(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
