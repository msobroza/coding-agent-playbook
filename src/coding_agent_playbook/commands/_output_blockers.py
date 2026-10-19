"""What stops a write of sync output, named with exit 1 instead of a traceback (SPEC §12.2).

Each adapter writes its files under fixed directories (``.claude/commands/``,
``.continue/rules/``, ``AGENTS.md`` at the root). Four things on the real tree
stop such a write, and the engine never removes one, since it cannot tell
whose it is:

- a dangling symlink on the way (``.claude/commands -> ../tools/cc`` with no
  ``tools/cc``): ``mkdir`` through it raises ``FileExistsError``, a write
  below it ``FileNotFoundError``;
- a non-directory where a directory goes (a file, or a link to one, at
  ``.claude/commands``): ``FileExistsError`` or ``NotADirectoryError``;
- a directory where the output file goes (``AGENTS.md/``): ``IsADirectoryError``;
- a FIFO, socket or device where the output file goes: the owned output writers
  refuse it before ``open()`` would block or fail (``generated_output.output_io``).

Write mode attributes the failed write's ``OSError`` to the blocker on its path
(:func:`blocker_in`) and exits 1 naming it (:func:`report_blocker`); ``--check``
predicts the same blocker for a missing file (:func:`write_blocker`). This runs
when a write fails, not as a preflight over every declared output directory: a
link the render never writes through (a dangling ``.claude/skills`` with no
skills enabled) must not stop the sync. Inside a native skill directory the
skill writer settles blockers itself (SPEC §10.8), and a dangling skills root it
skips with a warning (``adapters/_skill_writer.py``).
"""

from __future__ import annotations

import errno
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from coding_agent_playbook.generated_output.output_io import special_file_kind
from coding_agent_playbook.generated_output.symlinks import (
    is_dangling_symlink,
    unresolvable_link_errno,
)

#: The errnos a blocker causes; anything else (EACCES, ENOSPC, EROFS, ...) keeps its traceback.
_BLOCKER_ERRNOS: Final = frozenset(
    {
        errno.EEXIST,
        errno.ENOENT,
        errno.ENOTDIR,
        errno.ELOOP,
        errno.EISDIR,
        errno.ENXIO,
        errno.EOPNOTSUPP,
    }
)
#: What a FIFO, socket or device at the path reports: ``generated_output.output_io``'s
#: refusal, or ``open()`` on a socket.
_SPECIAL_ERRNOS: Final = frozenset({errno.ENXIO, errno.EOPNOTSUPP})
_MOVE_REMEDY: Final = "Move or rename it (sync never deletes it)"
_LINK_REMEDY: Final = "Re-point or remove the link"
_DANGLING_REMEDY: Final = "Create the link's target, or re-point or remove the link"
_INSIDE: Final = "but sync writes generated files inside it"
_AT: Final = "but sync writes a generated file at that path"


@dataclass(frozen=True)
class OutputBlocker:
    """The entry on the real tree that stops a write of sync output.

    ``shown`` is its repo-relative spelling and ``reason`` what is wrong with it
    (``problem`` joins the two); ``remedy`` is the fix, without the command to re-run.

    Example::

        OutputBlocker(repo / "AGENTS.md", "AGENTS.md",
                      "is a directory, but sync writes a generated file at that path",
                      "Move or rename it (sync never deletes it)")
    """

    path: Path
    shown: str
    reason: str
    remedy: str

    @property
    def problem(self) -> str:
        """``<shown> <reason>``: the sentence write mode prints after ``error:``."""
        return f"{self.shown} {self.reason}"


def blocker_in(exc: OSError, repo_root: Path) -> OutputBlocker | None:
    """The blocker inside ``repo_root`` that made the write ``exc`` reports fail, else ``None``.

    Only an errno a blocker causes counts, and only an entry on the way to (or
    at) a path ``exc`` names. Never raises.

    Example: ``blocker_in(FileExistsError(17, "File exists", str(repo / ".claude/commands")), repo)``
    names ``.claude/commands`` when it is a file or a dangling link.
    """
    if exc.errno not in _BLOCKER_ERRNOS:
        return None
    for path in _named_paths(exc):
        found = _parent_blocker(path, repo_root) or _failed_leaf(path, repo_root, exc.errno)
        if found is not None:
            return found
    return None


def write_blocker(
    path: Path, repo_root: Path, *, replaces_path: bool = False
) -> OutputBlocker | None:
    """``--check``: the blocker a write of the file ``path`` would stop on, else ``None``.

    A dangling link or a non-directory at a directory on the way always stops
    it, and so does a directory, a FIFO, a socket or a device at ``path``. A
    dangling link at ``path`` only when it loops or its target's directory is
    missing too: otherwise the write creates the target through it
    (``AGENTS.md -> docs/AGENTS.md``). With ``replaces_path`` (an atomic
    ``os.replace``, as for the co-owned ``.claude/settings.json``) a dangling
    link at ``path`` is replaced, never a blocker.

    Example: ``write_blocker(repo / ".claude/commands/x.md", repo)`` names
    ``.claude/commands`` when it is a file.
    """
    return _parent_blocker(path, repo_root) or _predicted_leaf(path, repo_root, replaces_path)


def report_blocker(blocker: OutputBlocker, *, check: bool) -> int:
    """Explain the ``blocker`` a sync could not write past; return 1.

    ``--check`` prints ``Cannot verify <path>: it <reason>.``, the shape every
    check-mode refusal shares, so the stop gate's ``sync_check_findings`` reads
    the path from it.

    Example: ``return report_blocker(blocker, check=False)``.
    """
    if check:
        print(f"Cannot verify {blocker.shown}: it {blocker.reason}.")
        print(f"{blocker.remedy}, then re-run 'playbook sync --check'.")
        return 1
    print(f"error: {blocker.problem}", file=sys.stderr)
    print("error: playbook sync stopped before finishing.", file=sys.stderr)
    print(f"error: {blocker.remedy}, then re-run 'playbook sync'.", file=sys.stderr)
    return 1


def _named_paths(exc: OSError) -> list[Path]:
    """The ``str``/path-like ``filename`` and ``filename2`` of ``exc`` (never bytes or an fd)."""
    paths: list[Path] = []
    for name in (exc.filename, exc.filename2):
        if isinstance(name, os.PathLike):
            name = os.fspath(name)
        if isinstance(name, str):
            paths.append(Path(name))
    return paths


def _entries_down_to(path: Path, repo_root: Path) -> list[Path]:
    """Each entry from ``repo_root``'s child down to ``path``, as spelled; ``[]`` outside it."""
    root = Path(os.path.abspath(repo_root))
    try:
        parts = Path(os.path.abspath(path)).relative_to(root).parts
    except ValueError:
        return []
    return [root.joinpath(*parts[: depth + 1]) for depth in range(len(parts))]


def _parent_blocker(path: Path, repo_root: Path) -> OutputBlocker | None:
    """A dangling link or a non-directory at a directory between ``repo_root`` and ``path``."""
    for entry in _entries_down_to(path, repo_root)[:-1]:
        if is_dangling_symlink(entry):
            return _dangling(entry, repo_root)
        if os.path.exists(entry) and not os.path.isdir(entry):
            return _described(entry, repo_root, "not a directory", _INSIDE)
    return None


def _failed_leaf(path: Path, repo_root: Path, code: int | None) -> OutputBlocker | None:
    """What at ``path`` itself explains a write that failed with ``code``."""
    entries = _entries_down_to(path, repo_root)
    if not entries:
        return None
    leaf, kind = entries[-1], special_file_kind(entries[-1], reading=True)
    if is_dangling_symlink(leaf):
        return _dangling(leaf, repo_root)
    if code == errno.EEXIST and os.path.exists(leaf) and not os.path.isdir(leaf):
        return _described(leaf, repo_root, "not a directory", _INSIDE)  # ``mkdir`` of an output dir
    if code == errno.EISDIR and os.path.isdir(leaf):
        return _described(leaf, repo_root, "a directory", _AT)
    if code in _SPECIAL_ERRNOS and kind is not None:
        return _described(leaf, repo_root, f"a {kind}, not a regular file", _AT)
    return None


def _predicted_leaf(path: Path, repo_root: Path, replaces_path: bool) -> OutputBlocker | None:
    """What at ``path`` itself would stop writing the file there."""
    entries = _entries_down_to(path, repo_root)
    if not entries:
        return None
    leaf, kind = entries[-1], special_file_kind(entries[-1])
    if os.path.isdir(leaf):
        return _described(leaf, repo_root, "a directory", _AT)
    if kind is not None:
        return _described(leaf, repo_root, f"a {kind}, not a regular file", _AT)
    code = None if replaces_path else unresolvable_link_errno(leaf)
    if code is None:
        return None
    target_dir = os.path.dirname(os.path.realpath(leaf))
    looped_or_lost = code == errno.ELOOP or not os.path.isdir(target_dir)
    return _dangling(leaf, repo_root) if looped_or_lost else None


def _shown(entry: Path, repo_root: Path) -> str:
    """``entry`` relative to ``repo_root`` as spelled, POSIX (as is if outside)."""
    try:
        return Path(os.path.abspath(entry)).relative_to(os.path.abspath(repo_root)).as_posix()
    except ValueError:
        return entry.as_posix()


def _link_target(link: Path) -> str:
    """The target stored in ``link`` (what ``ls -l`` shows); ``?`` if it changed since."""
    try:
        return os.readlink(link)
    except OSError:
        return "?"


def _dangling(link: Path, repo_root: Path) -> OutputBlocker:
    target = _link_target(link)
    if unresolvable_link_errno(link) == errno.ELOOP:
        state = "is a symbolic link loop"
    elif os.path.islink(os.path.join(os.path.dirname(link), target)):
        state = "is itself a dangling symbolic link"
    else:
        state = "does not exist"
    reason = f"is a dangling symbolic link: its target {target} {state}"
    return OutputBlocker(link, _shown(link, repo_root), reason, _DANGLING_REMEDY)


def _described(entry: Path, repo_root: Path, what: str, tail: str) -> OutputBlocker:
    """``<entry> is <what>, <tail>``; for a link ``… is a symbolic link to T, which is <what>, <tail>``."""
    shown = _shown(entry, repo_root)
    if os.path.islink(entry):
        reason = f"is a symbolic link to {_link_target(entry)}, which is {what}, {tail}"
        return OutputBlocker(entry, shown, reason, _LINK_REMEDY)
    return OutputBlocker(entry, shown, f"is {what}, {tail}", _MOVE_REMEDY)
