"""Lockfile-driven removal of stale generated outputs (SPEC §10.1, §12.2, §14.4).

Adapter ``cleanup_stale`` only recognises its own engine files (sentinel-tagged
ones, plus the scripts agent_harness's previous manifest records), so outputs
written without a sentinel (native skills' ``SKILL.md``, ``scripts/`` and
``references/`` byte copies) were never removed once their artifact, pack, or
adapter went away. The previous lockfile is the ownership record that closes
that gap: from schema 2 on (``lockfile.FIRST_OWNERSHIP_SCHEMA_VERSION``) it
lists only files an earlier sync generated, with the hash each had then
(:mod:`coding_agent_playbook.output_ownership`). A listed file the current sync
did not write is stale, and it is deleted only while it is still byte-identical
to what the engine wrote. Stale entries of an older lockfile are reported, never
deleted, because that format could also list files the engine did not generate.

Stdlib only. Never raises on an unreadable file or a malformed entry; it is
skipped instead.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Literal

from coding_agent_playbook.lockfile import FIRST_OWNERSHIP_SCHEMA_VERSION, compute_hash
from coding_agent_playbook.output_ownership import repo_relative_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.lockfile import LockEntry, Lockfile

#: Files owned by the StateSource (config, local config, lockfile). Never swept,
#: even when a hand-edited lockfile lists them. Keep in sync with the filename
#: constants on ``sources.filesystem.FileSystemStateSource``.
STATE_FILE_NAMES: tuple[str, ...] = (
    ".coding-agent-playbook.toml",
    ".coding-agent-playbook.local.toml",
    ".coding-agent-playbook.lock",
)

#: The repo-local canonical source root (``FileSystemArtifactSource`` reads
#: ``<repo>/playbook/``). Sync never writes there, so it is never swept.
ARTIFACT_SOURCE_DIR_NAME = "playbook"

# All keys are compared case-folded: on a case-insensitive filesystem
# ``.GIT/HEAD`` or ``.Coding-Agent-...`` names the same file.
_STATE_FILE_KEYS: frozenset[str] = frozenset(name.casefold() for name in STATE_FILE_NAMES)
# Version-control internals: deleting e.g. ``.git/HEAD`` breaks the checkout.
_VCS_DIR_KEYS: frozenset[str] = frozenset({".git", ".hg", ".svn"})

# O_NOFOLLOW makes the final open refuse a symlink swapped in after the lstat
# check. Windows has no such flag; the lstat check alone guards it there.
_OPEN_FLAGS: int = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)

# Expected errors from path syscalls: OSError (I/O), ValueError (an embedded
# NUL), RuntimeError (a symlink loop in ``Path.resolve`` on Python 3.12).
_PATH_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError, RuntimeError)

_FileIdentity = tuple[int, int]
_Verdict = Literal["removed", "kept_modified", "kept_unverified", "skipped"]


@dataclass(frozen=True)
class StaleSweep:
    """What :func:`sweep_stale_outputs` did (or, with ``dry_run``, would do).

    ``removed`` holds the deleted files; ``kept_modified`` the stale files kept
    because they were edited after the sync that generated them; and
    ``kept_unverified`` the unmodified stale files kept because only a lockfile
    older than schema 2 lists them. All are ``repo_root / <lockfile path>``,
    sorted by lockfile path.
    """

    removed: tuple[Path, ...]
    kept_modified: tuple[Path, ...]
    kept_unverified: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _SweepScope:
    """The per-sweep facts every entry is judged against."""

    repo_root: Path
    root: Path  # repo_root.resolve()
    protected: frozenset[_FileIdentity]  # files written this sync + state files
    trusted: bool  # the lockfile is an ownership record (schema >= 2)
    dry_run: bool


def sweep_stale_outputs(
    previous: Lockfile | None,
    written: Iterable[Path],
    repo_root: Path,
    *,
    dry_run: bool = False,
) -> StaleSweep:
    """Delete outputs ``previous`` recorded that this sync did not write.

    An entry is deleted only when its path is relative, posix, ``..``-free and
    names no state file, no ``.git``/``.hg``/``.svn`` part and nothing under
    ``playbook/``; the file is a regular file inside ``repo_root`` reached
    through no symlink (itself or any directory below ``repo_root``); it is not
    the same file (device + inode) as any path in ``written``; its sha256 still
    equals the recorded one; and ``previous`` is schema 2 or newer. An edited
    stale file is kept and reported in ``kept_modified``, an unmodified one of
    an older lockfile in ``kept_unverified``. Missing, unreadable, and malformed
    entries are skipped. Directories a deletion empties are pruned bottom-up,
    never ``repo_root`` itself. ``dry_run`` deletes and prunes nothing and
    reports what a real sweep would delete in ``removed``.

    Example::

        previous = state_source.load_lockfile()  # before adapters write
        written = [...]  # every path the adapters wrote this sync
        sweep = sweep_stale_outputs(previous, written, repo_root)
        print(len(sweep.removed), [str(p) for p in sweep.kept_modified])
    """
    if previous is None:
        return StaleSweep(removed=(), kept_modified=())
    scope = _SweepScope(
        repo_root=repo_root,
        root=repo_root.resolve(),
        protected=_identities([*written, *(repo_root / name for name in STATE_FILE_NAMES)]),
        trusted=_is_ownership_record(previous),
        dry_run=dry_run,
    )
    found: dict[_Verdict, list[PurePosixPath]] = {}
    for rel, sha256 in _safe_entries(previous.entries):
        found.setdefault(_sweep_one(rel, sha256, scope), []).append(rel)
    removed = found.get("removed", [])
    if not dry_run:
        prune_empty_parents(repo_root, [repo_root.joinpath(*rel.parts) for rel in removed])

    def _paths(verdict: _Verdict) -> tuple[Path, ...]:
        return tuple(repo_root.joinpath(*rel.parts) for rel in found.get(verdict, []))

    return StaleSweep(
        removed=_paths("removed"),
        kept_modified=_paths("kept_modified"),
        kept_unverified=_paths("kept_unverified"),
    )


def prune_empty_parents(repo_root: Path, removed: Iterable[Path]) -> None:
    """Remove the now-empty parent directories of each removed file, bottom-up.

    ``removed`` holds paths under ``repo_root``; any other path is ignored.
    Each chain stops at the first directory that is reached through a symlink
    or that ``os.rmdir`` refuses (not empty, permissions), and never reaches
    ``repo_root``.

    Example::

        removed = adapter.cleanup_stale(written_paths, repo_root)
        prune_empty_parents(repo_root, removed)
    """
    root = repo_root.resolve()
    for path in removed:
        rel = repo_relative_path(path, repo_root, root)
        if rel is None:
            continue
        for parent in list(rel.parents)[:-1]:
            directory = root.joinpath(*parent.parts)
            if not _reached_without_symlinks(directory, directory) or not _rmdir(directory):
                break


def _rmdir(directory: Path) -> bool:
    try:
        os.rmdir(directory)
    except _PATH_ERRORS:
        return False
    return True


def _is_ownership_record(lockfile: Lockfile) -> bool:
    """True from schema 2 on, whose entries list only engine-generated files."""
    version = lockfile.schema_version
    is_int = isinstance(version, int) and not isinstance(version, bool)
    return is_int and version >= FIRST_OWNERSHIP_SCHEMA_VERSION


def _safe_entries(entries: Iterable[LockEntry]) -> list[tuple[PurePosixPath, str]]:
    """``(relative path, sha256)`` of every safe, well-typed entry, sorted by path."""
    safe: list[tuple[PurePosixPath, str]] = []
    for entry in entries:
        rel = _safe_relative_path(entry.path)
        if rel is not None and isinstance(entry.sha256, str):
            safe.append((rel, entry.sha256))
    return sorted(safe, key=lambda pair: pair[0])


def _safe_relative_path(raw: object) -> PurePosixPath | None:
    """Parse a lockfile path; ``None`` unless it is a relative, posix, ``..``-free
    string naming nothing the engine never writes (see :func:`_is_off_limits`)."""
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        return None
    if PureWindowsPath(raw).drive:
        return None
    rel = PurePosixPath(raw)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts or _is_off_limits(rel):
        return None
    return rel


def _is_off_limits(rel: PurePosixPath) -> bool:
    """True for a state file, VCS internals, or the repo-local canonical sources."""
    keys = [part.casefold() for part in rel.parts]
    if keys[-1] in _STATE_FILE_KEYS or keys[0] == ARTIFACT_SOURCE_DIR_NAME:
        return True
    return any(key in _VCS_DIR_KEYS for key in keys)


def _sweep_one(rel: PurePosixPath, sha256: str, scope: _SweepScope) -> _Verdict:
    """Delete one stale entry if every guard holds; say what happened to it."""
    candidate = scope.repo_root.joinpath(*rel.parts)
    if not _reached_without_symlinks(candidate, scope.root.joinpath(*rel.parts)):
        return "skipped"
    snapshot = _read_regular_file(candidate)
    if snapshot is None or snapshot[0] in scope.protected:
        return "skipped"
    if compute_hash(snapshot[1]) != sha256:
        return "kept_modified"
    if not scope.trusted:
        return "kept_unverified"
    if scope.dry_run:
        return "removed"
    try:
        candidate.unlink()
    except _PATH_ERRORS:
        return "skipped"
    return "removed"


def _reached_without_symlinks(candidate: Path, expected: Path) -> bool:
    """True when ``candidate`` resolves to ``expected`` (``resolved root / rel``):
    no component below the repo root, the file included, is a symlink."""
    try:
        return candidate.resolve() == expected
    except _PATH_ERRORS:
        return False


def _read_regular_file(candidate: Path) -> tuple[_FileIdentity, bytes] | None:
    """Return ``(identity, content)`` of a regular non-symlink file, else ``None``."""
    try:
        if not stat.S_ISREG(os.lstat(candidate).st_mode):
            return None
        fd = os.open(candidate, _OPEN_FLAGS)
    except _PATH_ERRORS:
        return None
    try:
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            content = handle.read()
    except _PATH_ERRORS:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return (info.st_dev, info.st_ino), content


def _identities(paths: Iterable[Path]) -> frozenset[_FileIdentity]:
    """``(st_dev, st_ino)`` of every existing path; unreadable paths are skipped.

    Identity, not path text, decides "written this sync": a hard link or a
    case-only rename on a case-insensitive filesystem gives one file two paths.
    """
    found: set[_FileIdentity] = set()
    for path in paths:
        try:
            info = os.stat(path)
        except _PATH_ERRORS:
            continue
        found.add((info.st_dev, info.st_ino))
    return frozenset(found)
