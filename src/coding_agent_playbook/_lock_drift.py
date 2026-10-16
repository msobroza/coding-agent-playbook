"""Drift between ``.coding-agent-playbook.lock`` and the files on disk (SPEC §14.4; specs/prK-hook-pack.md §E.1).

The one definition of lockfile drift, shared by ``playbook check`` (its Drift
section) and the hook runtime (the ``drift`` Stop stage and the session-start
briefing), so humans and hooks never disagree. ``lockfile`` re-exports it.

- A **whole-file** entry drifts when its file is missing (or not a regular
  file), no longer hashes to the recorded ``sha256``, or lost the exec bit it
  was recorded with (POSIX). A symbolic link is never followed: the engine
  never writes one, so a link where an output was is a hash mismatch.
- A **scoped** ``json:<pointer>`` entry owns one element of a JSON file it
  shares with the user (§C.2.6). It is present when some element of the array
  at its pointer has the recorded canonical hash (``_canonical_json``), so user
  keys, reformatting and key order never count. ``playbook check`` passes the
  strict Claude settings parser and the "edited" probe; the runtime uses the
  stdlib defaults.

An entry outside the repository (absolute, or with a ``..`` step) is never
read, and ``skip`` keeps secret paths unread (SPEC §17.3). Stdlib and
``_canonical_json`` only: the runtime imports this on ``stop`` and
``session_start`` (§D.1 branch-local row), so it may not pull jinja2 or adapters.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook._canonical_json import array_at, element_sha256

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from pathlib import Path

    from coding_agent_playbook.lockfile import LockEntry, Lockfile

__all__ = [
    "DriftItem",
    "DriftKind",
    "EditedProbe",
    "ScopedParser",
    "ScopedUnreadable",
    "drift_entries",
    "managed_drift",
    "parse_json_document",
]

type DriftKind = Literal[
    "missing", "hash_mismatch", "mode_mismatch", "managed_missing", "managed_edited", "unreadable"
]
#: ``(file bytes or None when absent, repo-relative path) -> parsed document``;
#: raises :class:`ScopedUnreadable` for a file that cannot be judged.
type ScopedParser = Callable[[bytes | None, str], object]
#: ``(pointer, array, element hashes, recorded hashes) -> bool``: whether a
#: missing managed element was hand-edited rather than removed.
type EditedProbe = Callable[[str, Sequence[object], Sequence[str], frozenset[str]], bool]

_JSON_SCOPE: Final = "json:"
_LINES: Final = {
    "missing": "missing: {path}",
    "hash_mismatch": "hash mismatch: {path}",
    "mode_mismatch": "mode mismatch: {path} (expected executable)",
    "managed_missing": "managed entry missing: {path}#{pointer}",
    "managed_edited": "managed entry edited: {path}#{pointer}",
    "unreadable": "unreadable: {path} ({detail})",
}


class ScopedUnreadable(ValueError):
    """A shared JSON file that cannot be judged element by element; ``detail`` says why.

    Example: ``ScopedUnreadable("line 1, col 3: Expecting value").detail``.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class DriftItem:
    """One drifted lock entry: ``pointer`` names a scoped entry's array, ``detail`` an error.

    Example::

        >>> DriftItem("AGENTS.md", "hash_mismatch").line()
        'hash mismatch: AGENTS.md'
    """

    path: str
    kind: DriftKind
    pointer: str = ""
    detail: str = ""

    def line(self) -> str:
        """The ``playbook check`` Drift line, without its indentation."""
        return _LINES[self.kind].format(path=self.path, pointer=self.pointer, detail=self.detail)


def drift_entries(
    lockfile: Lockfile,
    repo_root: Path,
    *,
    skip: Callable[[str], bool] | None = None,
    parse_scoped: ScopedParser | None = None,
    edited: EditedProbe | None = None,
) -> list[DriftItem]:
    """Every drifted entry of ``lockfile``: whole-file entries in order, then scoped ones by file.

    ``skip(rel)`` leaves an entry unread and unreported (secret paths);
    ``parse_scoped`` defaults to :func:`parse_json_document`.

    Example::

        >>> drift_entries(Lockfile(2, "0.2.0", "", entries=[]), Path("."))
        []
    """
    entries = [e for e in lockfile.entries if _inside(e.path) and not (skip and skip(e.path))]
    items = [item for e in entries if not e.scope if (item := _whole_file(repo_root, e))]
    scoped = [e for e in entries if e.scope.startswith(_JSON_SCOPE)]
    items.extend(_scoped(repo_root, scoped, parse_scoped or parse_json_document, edited))
    return items


def managed_drift(
    doc: object, entries: Iterable[LockEntry], *, edited: EditedProbe | None = None
) -> list[DriftItem]:
    """The scoped ``entries`` no element of ``doc`` matches by canonical hash, in entry order.

    Example::

        >>> managed_drift({}, [])
        []
    """
    scoped = [entry for entry in entries if entry.scope.startswith(_JSON_SCOPE)]
    items: list[DriftItem] = []
    for entry in scoped:
        pointer = entry.scope.removeprefix(_JSON_SCOPE)
        array = array_at(doc, pointer)
        hashes = [element_sha256(item) for item in array]
        if entry.sha256 in hashes:
            continue
        recorded = frozenset(other.sha256 for other in scoped if other.scope == entry.scope)
        hand_edited = edited is not None and edited(pointer, array, hashes, recorded)
        kind: DriftKind = "managed_edited" if hand_edited else "managed_missing"
        items.append(DriftItem(entry.path, kind, pointer=pointer))
    return items


def parse_json_document(data: bytes | None, rel: str) -> object:
    """``data`` as JSON (a UTF-8 BOM allowed); an absent or blank file is ``{}``.

    Raises :class:`ScopedUnreadable` naming the line and column of a syntax error.

    Example::

        >>> parse_json_document(None, "x.json"), parse_json_document(b'{"a": 1}', "x.json")
        ({}, {'a': 1})
    """
    if data is None:
        return {}
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ScopedUnreadable(f"not valid UTF-8 at byte {exc.start}") from None
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScopedUnreadable(f"line {exc.lineno}, col {exc.colno}: {exc.msg}") from None
    except RecursionError:
        raise ScopedUnreadable(f"{rel} nests too deeply to read") from None


def _inside(rel: str) -> bool:
    """Whether ``rel`` stays in the repository: relative, with no ``..`` step."""
    parts = rel.replace("\\", "/").split("/")
    return bool(rel) and not os.path.isabs(rel) and ".." not in parts


def _whole_file(root: Path, entry: LockEntry) -> DriftItem | None:
    """The drift of one whole-file entry, read without following a symbolic link."""
    path = root / entry.path
    try:
        info = os.lstat(path)
    except OSError:
        return DriftItem(entry.path, "missing")
    if stat.S_ISLNK(info.st_mode):
        return DriftItem(entry.path, "hash_mismatch")
    if not stat.S_ISREG(info.st_mode):
        return DriftItem(entry.path, "missing")
    try:
        data = _read_no_follow(path)
    except OSError as exc:
        return DriftItem(entry.path, "unreadable", detail=exc.strerror or str(exc))
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        return DriftItem(entry.path, "hash_mismatch")
    if entry.executable and os.name == "posix" and not info.st_mode & 0o111:
        return DriftItem(entry.path, "mode_mismatch")
    return None


def _scoped(
    root: Path, entries: Sequence[LockEntry], parse: ScopedParser, edited: EditedProbe | None
) -> list[DriftItem]:
    """The managed-element drift of each shared file, one ``unreadable`` line when it cannot parse."""
    by_path: dict[str, list[LockEntry]] = {}
    for entry in entries:
        by_path.setdefault(entry.path, []).append(entry)
    items: list[DriftItem] = []
    for rel, group in by_path.items():
        try:
            doc = parse(_read_optional(root / rel), rel)
        except ScopedUnreadable as exc:
            items.append(DriftItem(rel, "unreadable", detail=exc.detail))
            continue
        except OSError as exc:  # a directory, no permission: one line, never a traceback
            items.append(DriftItem(rel, "unreadable", detail=exc.strerror or str(exc)))
            continue
        items.extend(managed_drift(doc, group, edited=edited))
    return items


def _read_optional(path: Path) -> bytes | None:
    """``path``'s bytes, ``None`` when absent; a symbolic link is unreadable, never followed."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise ScopedUnreadable("a symbolic link; not read")
    if not stat.S_ISREG(info.st_mode):  # a directory, or a FIFO that would block the read
        raise ScopedUnreadable("not a regular file")
    return _read_no_follow(path)


def _read_no_follow(path: Path) -> bytes:
    """Read ``path`` refusing a link swapped in after the ``lstat`` (``O_NOFOLLOW`` where known)."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read()
