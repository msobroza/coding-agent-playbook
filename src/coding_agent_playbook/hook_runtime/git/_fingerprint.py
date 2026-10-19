"""The working-tree fingerprint (specs/prK-lifecycle-hooks.md §D.5.3, D-8).

**Tree mode** (git ≥ 2.26) computes a real tree id in a temp index, so the
user's index is never touched:

1. copy ``<git_dir>/index`` to ``<state>/tmp/index.<pid>``, keeping its mtime
   so git's racy-clean check still holds (or start empty);
2. exclude every tracked or untracked path matching ``secret_path_globs`` and
   every untracked file over ``max_file_bytes``: they are stat'ed, never read;
3. ``git add -A`` the rest through ``--pathspec-from-file`` with one
   ``:(exclude,literal)`` pathspec per excluded path, then ``git write-tree``;
4. ``aux`` hashes the sorted ``(path, size, mtime_ns)`` of the excluded paths.

``git add -A`` writes loose blobs for changed files, which ``git gc`` prunes
(OQ-23, accepted). Secret files never reach the object store.

**Stat mode** (git < 2.26, no ``--pathspec-from-file``) hashes
``git status --porcelain=v2 -z`` plus the stat of each listed path; an empty
status means unchanged, and there is no tree id.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.paths import fold_key
from coding_agent_playbook.hook_runtime.git.parse import parse_status_paths, split_z
from coding_agent_playbook.hook_runtime.git.safe_git import Fingerprint
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from coding_agent_playbook.hook_runtime.git.safe_git import SafeGit

__all__ = ["MIN_TREE_MODE_VERSION", "working_tree_fingerprint"]

#: ``git add --pathspec-from-file`` arrived in git 2.26.
MIN_TREE_MODE_VERSION: Final = (2, 26, 0)
_MISSING: Final = (-1, -1)


def working_tree_fingerprint(git: SafeGit) -> Fingerprint:
    """The fingerprint of ``git``'s worktree; raises ``GitError`` or ``OSError``.

    Example::

        >>> working_tree_fingerprint(git).key  # doctest: +SKIP
        '9b1d3191fdbfae04319d70478cfa345ad9a8f2bf'
    """
    if git.version() < MIN_TREE_MODE_VERSION:
        return _stat_fingerprint(git)
    return _tree_fingerprint(git)


def _tree_fingerprint(git: SafeGit) -> Fingerprint:
    with _temp_index(git) as index:
        tracked = split_z(git.run(["ls-files", "-z"], index_file=index).stdout)
        excluded = _excluded(git, tracked, git.ls_untracked())
        git.run(
            ["add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"],
            input=_pathspec(excluded),
            index_file=index,
        )
        tree = git.run(["write-tree"], index_file=index).stdout.decode("ascii").strip()
    aux = _aux(git.repo.worktree_root, excluded)
    unchanged = not aux and tree == git.head_tree()
    return Fingerprint(tree_id=tree, aux=aux, mode="tree", unchanged_vs_head=unchanged)


def _stat_fingerprint(git: SafeGit) -> Fingerprint:
    status = git.run(
        ["status", "--porcelain=v2", "-z", "--untracked-files=all", "--no-renames"]
    ).stdout
    digest = hashlib.sha256(status)
    for path, (size, mtime) in _stats(git.repo.worktree_root, parse_status_paths(status)):
        digest.update(f"\x00{path}\x00{size}\x00{mtime}".encode("utf-8", "surrogateescape"))
    return Fingerprint(
        tree_id=None, aux="", mode="stat", unchanged_vs_head=not status, digest=digest.hexdigest()
    )


@contextmanager
def _temp_index(git: SafeGit) -> Iterator[str]:
    """A private copy of the user's index, deleted afterwards whatever happens."""
    directory, owned = _temp_dir(git)
    index = directory / f"index.{os.getpid()}"
    try:
        index.unlink(missing_ok=True)
        _copy_index(Path(git.repo.git_dir) / "index", index)
        yield str(index)
    finally:
        index.unlink(missing_ok=True)
        Path(f"{index}.lock").unlink(missing_ok=True)
        if owned:
            shutil.rmtree(directory, ignore_errors=True)


def _copy_index(source: Path, target: Path) -> None:
    """Copy the index *and its mtime*; a missing index means starting empty.

    git's racy-clean check compares each entry's mtime with the index file's
    own mtime. A fresh copy is newer than every entry, so a file rewritten at
    the same size within the same timestamp tick as the last index write
    would look clean and keep its stale blob in the fingerprint.
    """
    try:
        info = os.stat(source)
    except FileNotFoundError:
        return
    shutil.copyfile(source, target)
    os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))


def _temp_dir(git: SafeGit) -> tuple[Path, bool]:
    """``(<state>/tmp, False)``, or a fresh system temp dir it owns when stateless."""
    if git.state is not None:
        with suppress(StateUnavailable):
            return git.state.private_dir("tmp"), False
    import tempfile  # stateless only

    return Path(tempfile.mkdtemp(prefix="playbook-hooks-")), True


def _excluded(git: SafeGit, tracked: Iterable[str], untracked: Iterable[str]) -> list[str]:
    untracked = list(untracked)
    secret = {p for p in (*tracked, *untracked) if _is_secret(git, p)}
    oversized = {p for p in untracked if _size(git.repo.worktree_root, p) > git.max_file_bytes}
    return sorted(secret | oversized)


def _is_secret(git: SafeGit, repo_rel: str) -> bool:
    return git.secret_paths is not None and git.secret_paths.matches(
        fold_key(repo_rel, git.platform)
    )


def _size(root: str, repo_rel: str) -> int:
    try:
        info = os.lstat(os.path.join(root, repo_rel))
    except OSError:
        return 0
    return info.st_size if stat.S_ISREG(info.st_mode) else 0


def _pathspec(excluded: Iterable[str]) -> bytes:
    specs = [".", *(f":(exclude,literal){path}" for path in excluded)]
    return b"".join(spec.encode("utf-8", "surrogateescape") + b"\x00" for spec in specs)


def _stats(root: str, paths: Iterable[str]) -> Iterator[tuple[str, tuple[int, int]]]:
    for path in sorted(paths):
        try:
            info = os.lstat(os.path.join(root, path))
        except OSError:
            yield path, _MISSING
            continue
        yield path, (info.st_size, info.st_mtime_ns)


def _aux(root: str, excluded: list[str]) -> str:
    """sha256 over the excluded paths' stat; ``""`` when nothing was excluded."""
    if not excluded:
        return ""
    digest = hashlib.sha256()
    for path, (size, mtime) in _stats(root, excluded):
        digest.update(f"{path}\x00{size}\x00{mtime}\x00".encode("utf-8", "surrogateescape"))
    return digest.hexdigest()
