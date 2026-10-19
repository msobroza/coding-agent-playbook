"""Git-free repo discovery and path normalization (specs/prK-lifecycle-hooks.md §D.2.4).

Every guard compares paths through one ``NormalizedPath`` and its match
``key``. Repo discovery reads only the filesystem (``.git``, ``gitdir:``,
``commondir``, ``worktrees/*/gitdir``) and never spawns git: the hot path runs
no subprocess for a non-git call (D-6). ``platform`` and ``home`` are
parameters, so the darwin and win32 behaviour is testable on any host.
"""

from __future__ import annotations

import os
import posixpath
import re
import sys
from dataclasses import dataclass

from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo

__all__ = ["FOLDING_PLATFORMS", "NormalizedPath", "find_repo", "fold_key", "normalize_path"]

#: Platforms whose default filesystems compare names case-insensitively (§D.2.4 step 6).
FOLDING_PLATFORMS = frozenset({"darwin", "win32"})

_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_GITDIR_PREFIX = "gitdir:"
_FIRST_LINE_MAX_CHARS = 4096


# --- repo discovery -------------------------------------------------------------------


def find_repo(start: str) -> RepoInfo | None:
    """The repository holding ``start``, discovered the way git does, or ``None`` outside git.

    Walks up to the first ancestor holding ``.git``: a directory is the git
    dir; a file names it with ``gitdir: <path>`` (a linked worktree). The
    ``commondir`` file inside the git dir names the shared common dir. A
    ``.git`` file without a ``gitdir:`` line means no repository, so hooks
    stay inert. The result agrees with
    ``git rev-parse --git-dir --git-common-dir --show-toplevel``.

    Example::

        >>> find_repo("/") is None
        True
    """
    directory = os.path.realpath(start)
    while True:
        dot_git = os.path.join(directory, ".git")
        if os.path.isdir(dot_git):
            return _repo_info(directory, dot_git)
        if os.path.isfile(dot_git):
            git_dir = _gitdir_of(dot_git)
            return None if git_dir is None else _repo_info(directory, git_dir)
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _gitdir_of(dot_git_file: str) -> str | None:
    """The git dir a ``.git`` file names, resolved against the file's directory."""
    line = _first_line(dot_git_file)
    if line is None or not line.startswith(_GITDIR_PREFIX):
        return None
    return os.path.join(os.path.dirname(dot_git_file), line[len(_GITDIR_PREFIX) :].strip())


def _repo_info(worktree_root: str, git_dir: str) -> RepoInfo:
    """Build the ``RepoInfo`` of the worktree at ``worktree_root``."""
    real_git_dir = os.path.realpath(git_dir)
    common = _first_line(os.path.join(real_git_dir, "commondir"))
    common_dir = (
        os.path.realpath(os.path.join(real_git_dir, common.strip())) if common else real_git_dir
    )
    return RepoInfo(
        worktree_root=worktree_root,
        git_dir=real_git_dir,
        common_dir=common_dir,
        is_linked_worktree=common_dir != real_git_dir,
        sibling_roots=_sibling_roots(common_dir, worktree_root),
    )


def _sibling_roots(common_dir: str, own_root: str) -> tuple[str, ...]:
    """Every other worktree sharing ``common_dir``: the main checkout, then each linked one."""
    roots: list[str] = []
    if os.path.basename(common_dir) == ".git":
        roots.append(os.path.dirname(common_dir))
    admin = os.path.join(common_dir, "worktrees")
    try:
        names = sorted(os.listdir(admin))
    except OSError:
        names = []
    for name in names:
        gitdir = _first_line(os.path.join(admin, name, "gitdir"))
        if gitdir:
            dot_git = os.path.join(admin, name, gitdir.strip())
            roots.append(os.path.dirname(os.path.realpath(dot_git)))
    return tuple(root for root in dict.fromkeys(roots) if root != own_root)


def _first_line(path: str) -> str | None:
    """The first line of a small text file, or ``None`` when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.readline(_FIRST_LINE_MAX_CHARS).rstrip("\r\n")
    except (OSError, UnicodeDecodeError):
        return None


# --- normalization --------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizedPath:
    """One path argument, resolved and classified against the event's repository.

    ``path`` is the absolute, lexically normalized path; ``realpath`` has every
    symlink resolved. ``repo_rel`` is POSIX and relative to ``worktree_root``,
    the deepest worktree of the repository that holds the path (``"."`` for the
    root itself); it is ``None`` outside the repository. ``key`` is what globs
    match: ``repo_rel`` (else ``realpath``), NFC + case-folded on darwin and
    win32. ``nlink > 1`` is the hard-link signal that ``realpath`` cannot see.

    Example::

        >>> p = normalize_path("a.py", base="/r", repo=None, home=None, platform="linux")
        >>> (p.path, p.outside_repo)
        ('/r/a.py', True)
    """

    raw: str
    path: str
    realpath: str
    key: str
    repo_rel: str | None = None
    worktree_root: str | None = None
    sibling_worktree: bool = False
    is_symlink: bool = False
    exists: bool = False
    nlink: int = 0

    @property
    def same_repo(self) -> bool:
        """Whether the path lies in any worktree of the event's repository."""
        return self.repo_rel is not None

    @property
    def outside_repo(self) -> bool:
        """Whether the path lies outside every worktree of the event's repository."""
        return self.repo_rel is None


def normalize_path(
    raw: str, *, base: str, repo: RepoInfo | None, home: str | None, platform: str = sys.platform
) -> NormalizedPath:
    """Normalize one path argument through the seven §D.2.4 steps.

    Backslashes become ``/`` for win32 or a drive path; a leading ``~`` expands
    to ``home`` (no expansion when ``home`` is ``None``); a relative path joins
    ``base`` (the segment cwd for a Bash target, else the event cwd); symlinks
    and ``..`` resolve; the result classifies against ``repo``, including its
    sibling worktrees; one ``lstat`` gives ``exists`` and ``nlink``.

    Example::

        >>> normalize_path("~/.ssh/id_rsa", base="/r", repo=None, home="/home/dev",
        ...                platform="linux").path
        '/home/dev/.ssh/id_rsa'
    """
    text = _expand_home(_forward_slashes(raw, platform), home, platform)
    if not _is_absolute(text):
        text = posixpath.join(_forward_slashes(base, platform), text)
    lexical = posixpath.normpath(text)
    real, on_host = _resolve(lexical, platform)
    root, rel = _locate(real, repo, platform)
    exists, nlink = _stat_facts(real) if on_host else (False, 0)
    return NormalizedPath(
        raw=raw,
        path=lexical,
        realpath=real,
        key=fold_key(real if rel is None else rel, platform),
        repo_rel=rel,
        worktree_root=root,
        sibling_worktree=root is not None and repo is not None and root != _root_of(repo, platform),
        is_symlink=real != lexical,
        exists=exists,
        nlink=nlink,
    )


def fold_key(text: str, platform: str) -> str:
    """``text`` as a match key: NFC + case-folded on darwin and win32, else unchanged.

    ``fnmatch`` does not fold case on darwin and ``realpath`` does not fold it
    either, while both platforms' default filesystems do; over-matching on a
    case-sensitive volume is the safe direction for guards.

    Example::

        >>> fold_key(".ENV", "darwin")
        '.env'
    """
    if platform not in FOLDING_PLATFORMS:
        return text
    import unicodedata  # only the folding platforms pay for it (§D.1)

    return unicodedata.normalize("NFC", text).casefold()


def _forward_slashes(text: str, platform: str) -> str:
    """``text`` with ``\\`` separators turned into ``/`` for win32 and drive paths."""
    if platform == "win32" or _DRIVE_PATH.match(text):
        return text.replace("\\", "/")
    return text


def _expand_home(text: str, home: str | None, platform: str) -> str:
    """Expand a leading ``~`` (alone or as ``~/``) to ``home``."""
    if home is None or not (text == "~" or text.startswith("~/")):
        return text
    return _forward_slashes(home, platform).rstrip("/") + text[1:] or "/"


def _is_absolute(text: str) -> bool:
    return text.startswith("/") or _DRIVE_PATH.match(text) is not None


def _resolve(lexical: str, platform: str) -> tuple[str, bool]:
    """``(realpath, resolved_on_host)`` for an absolute, lexically normalized path."""
    if _DRIVE_PATH.match(lexical) and sys.platform != "win32":
        # A drive-letter path cannot name a file on a POSIX host (only an injected
        # win32 platform yields one here), so it stays lexical and is never stat'ed.
        return lexical, False
    return _forward_slashes(os.path.realpath(lexical), platform), True


def _root_of(repo: RepoInfo, platform: str) -> str:
    return _forward_slashes(repo.worktree_root, platform)


def _locate(real: str, repo: RepoInfo | None, platform: str) -> tuple[str | None, str | None]:
    """``(worktree_root, repo_rel)`` for the deepest worktree of ``repo`` holding ``real``."""
    if repo is None:
        return None, None
    best: tuple[str, str] | None = None
    for candidate in (repo.worktree_root, *repo.sibling_roots):
        root = _forward_slashes(candidate, platform)
        rel = _relative_to(real, root, platform)
        if rel is not None and (best is None or len(root) > len(best[0])):
            best = (root, rel)
    return best if best is not None else (None, None)


def _relative_to(path: str, root: str, platform: str) -> str | None:
    """``path`` relative to ``root`` compared per component (folded where needed), else None."""
    root_parts = root.rstrip("/").split("/")
    parts = path.split("/")
    head = parts[: len(root_parts)]
    if len(parts) < len(root_parts):
        return None
    if [fold_key(p, platform) for p in head] != [fold_key(p, platform) for p in root_parts]:
        return None
    return "/".join(parts[len(root_parts) :]) or "."


def _stat_facts(real: str) -> tuple[bool, int]:
    """``(exists, nlink)`` from one ``lstat``."""
    try:
        status = os.lstat(real)
    except OSError:
        return False, 0
    return True, status.st_nlink
