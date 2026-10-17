"""Engine-owned single files: written whole only when the path is the engine's.

Some outputs are one file at a fixed, user-visible path that ``playbook sync``
writes whole: the Claude Code launcher ``.claude/hooks/playbook/launch.sh`` and
the OpenCode shim ``.opencode/plugins/playbook-hooks.js`` (an adapter's
``runtime_outputs``), and the Claude Code rules file
``.claude/rules/coding-agent-playbook.md`` (SPEC §10.3.1). Those directories
also hold the user's own files, so the path is the engine's only when nothing
is there yet, or when the file there carries the sentinel line
(``_sentinel.file_has_sentinel``, the same predicate the stale-output scans and
hook guards decide on). Anything else is refused,
never overwritten (code review of claude/prk-hooks-impl, findings #1 and #2):

- a regular file without the sentinel line: a user file of the same name;
- anything that is not a regular file (a directory, a FIFO, a socket);
- a symlink at the path, or at any directory between it and the repo root:
  writing through it could land outside the repo or in the user's own file;
- a non-directory where a parent directory belongs.

``playbook sync`` runs :func:`check_engine_owned` on the real repo for every
file an adapter plans to write (``Adapter.planned_runtime_outputs``, plus the
rules file whenever ``claude_code`` is on) before any adapter writes, so a
refusal exits 1 with nothing written; the adapters write through
:func:`write_engine_owned`, which checks again. The ``.claude/CLAUDE.md`` stub
is overwritten whole whatever regular file it holds, but :func:`check_unlinked`
refuses it too when a symlink is on the way, when it is a hard link, or when
it is not a regular file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook._sentinel import file_has_sentinel

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = [
    "UserOwnedFileError",
    "check_engine_owned",
    "check_unlinked",
    "crosses_symlink",
    "write_engine_owned",
]

#: Why the entry at the path itself is refused (the first two by both checks
#: below, the hard link by :func:`check_unlinked` alone).
_LINK_REASON = "it is a symbolic link, and the engine never writes through one"
_NOT_REGULAR_REASON = "it is not a regular file"
_HARD_LINK_REASON = (
    "it is a hard link shared with another file, and the engine never writes through one"
)


class UserOwnedFileError(Exception):
    """An engine-owned path is held by the user; sync must exit 1 and write nothing.

    ``path`` is repo-relative POSIX and ``reason`` says what is in the way;
    ``str()`` is ``<path>: <reason>``, and :attr:`remedy` is the one fix (the
    engine never guesses whose file it is, so it never moves one itself).

    Example::

        UserOwnedFileError(".opencode/plugins/playbook-hooks.js", "it is a symbolic link")
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason

    @property
    def remedy(self) -> str:
        """The sentence telling the user what to do, without the command to re-run."""
        return f"Move or rename what is in the way (the engine writes {self.path} whole)"


def check_engine_owned(path: Path, repo_root: Path) -> None:
    """Raise :class:`UserOwnedFileError` unless writing ``path`` whole clobbers nothing of the user's.

    Only the directories strictly below ``repo_root`` are inspected: a symlink
    above it (``/tmp`` -> ``/private/tmp``) is how the repo is reached, not a
    user file. Reads at most the sentinel head of an existing regular file.

    Example: ``check_engine_owned(repo / ".claude/hooks/playbook/launch.sh", repo)``.
    """
    relative = _relative_posix(path, repo_root)
    reason = _parent_refusal(path, repo_root) or _file_refusal(path)
    if reason is not None:
        raise UserOwnedFileError(relative, reason)


def check_unlinked(path: Path, repo_root: Path) -> None:
    """Raise :class:`UserOwnedFileError` unless ``path`` is absent or an unshared regular file.

    For a file the engine overwrites whatever regular file it holds (the
    ``.claude/CLAUDE.md`` stub, SPEC §10.3.1), yet never through a link: a
    symlink at it or at a directory on the way, or a hard link. Writing in place
    truncates the shared inode, so ``.claude/CLAUDE.md -> ../AGENTS.md`` (review
    round 2) or the same file hard-linked to ``AGENTS.md`` (final review; the
    usual stand-in on Windows, where file symlinks need developer mode) turned
    ``AGENTS.md`` into the stub. A directory or a FIFO there is refused too: it
    crashed or hung the stub write after other adapters had written. The same
    parent walk as :func:`check_engine_owned`, without its sentinel test.

    Example: ``check_unlinked(repo / ".claude/CLAUDE.md", repo)``.
    """
    reason = _parent_refusal(path, repo_root) or _unlinked_file_refusal(path)
    if reason is not None:
        raise UserOwnedFileError(_relative_posix(path, repo_root), reason)


def write_engine_owned(path: Path, repo_root: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` (creating its parents) after :func:`check_engine_owned`; return it.

    Bytes, not text: ``write_text`` would turn LF into CRLF on Windows.

    Example: ``write_engine_owned(out / OPENCODE_SHIM_PATH, out, shim.encode("utf-8"))``.
    """
    check_engine_owned(path, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def crosses_symlink(path: Path, repo_root: Path) -> bool:
    """Whether ``path``, or a directory between it and ``repo_root``, is a symlink.

    The same walk as :func:`check_engine_owned` (nothing at or above
    ``repo_root`` counts), for a stale-output check: the engine never writes
    through a link, so a file reached through one is the user's.

    Example: ``crosses_symlink(repo / ".claude/rules/x.md", repo)`` (``True`` if ``.claude`` is a link).
    """
    return any(entry.is_symlink() for entry in _entries_down_to(path, repo_root))


def _entries_down_to(path: Path, repo_root: Path) -> Iterator[Path]:
    """Each entry from ``repo_root``'s child down to ``path`` itself, as spelled (nothing resolved)."""
    current = repo_root
    for part in path.relative_to(repo_root).parts:
        current = current / part
        yield current


def _relative_posix(path: Path, repo_root: Path) -> str:
    """``path`` relative to ``repo_root`` as spelled (nothing resolved), POSIX."""
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        raise ValueError(
            f"engine-owned path {path} is not under the repo root {repo_root}"
        ) from None


def _parent_refusal(path: Path, repo_root: Path) -> str | None:
    """Why a directory between ``repo_root`` and ``path`` makes it the user's, else None."""
    for current in _entries_down_to(path.parent, repo_root):
        shown = _relative_posix(current, repo_root)
        if current.is_symlink():
            return f"{shown} is a symbolic link, and the engine never writes through one"
        if not current.exists():
            return None  # nothing below a missing directory can be in the way
        if not current.is_dir():
            return f"{shown} is not a directory"
    return None


def _file_refusal(path: Path) -> str | None:
    """Why the entry at ``path`` itself is the user's, else None (absent or sentinel-tagged)."""
    if path.is_symlink():
        return _LINK_REASON
    if not path.exists():
        return None
    if not path.is_file():
        return _NOT_REGULAR_REASON
    if not file_has_sentinel(path):
        return "it exists without the playbook sentinel on line 1, so it is yours"
    return None


def _unlinked_file_refusal(path: Path) -> str | None:
    """Why the entry at ``path`` may not be overwritten in place, else None (absent or unshared)."""
    if path.is_symlink():
        return _LINK_REASON
    if not path.exists():
        return None
    if not path.is_file():
        return _NOT_REGULAR_REASON
    if path.stat().st_nlink > 1:
        return _HARD_LINK_REASON
    return None
