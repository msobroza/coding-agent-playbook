"""Path-only secret classification (SPEC §17.3; specs/prK-lifecycle-hooks.md §P7).

:func:`is_secret_path` decides from the path string alone whether a file holds
credentials. It never touches the filesystem (no ``open``, ``stat`` or symlink
resolution), so a caller can classify a path *before* deciding to read it.
Normalization is lexical only; callers that need symlink- or hard-link-aware
classification resolve the path first (§D.2.4). Stdlib-only: the hook
dispatcher imports this module on its hot path (§D.1).
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import sys

from coding_agent_playbook.security.patterns import SECRET_PATH_EXEMPT, SECRET_PATH_GLOBS

#: Platforms whose default filesystems compare names case-insensitively.
_CASE_FOLDING_PLATFORMS: frozenset[str] = frozenset({"darwin", "win32"})

_HOME_PREFIX = "~/"


def is_secret_path(
    path: str | os.PathLike[str],
    *,
    home: str | os.PathLike[str] | None = None,
    platform: str = sys.platform,
) -> bool:
    """Whether ``path`` names a credential file the engine must never read.

    A path is secret when it matches a ``SECRET_PATH_GLOBS`` entry and no
    ``SECRET_PATH_EXEMPT`` entry (``security/patterns.py`` documents the glob
    grammar). ``home`` anchors the ``~/`` globs and expands a leading ``~`` in
    ``path``; it defaults to the current user's home. ``platform`` selects
    case folding (darwin, win32) and ``\\`` separators (win32); it defaults to
    ``sys.platform`` and is injectable for tests.

    Example::

        >>> is_secret_path("deploy/.env", home="/home/dev")
        True
        >>> is_secret_path(".env.example", home="/home/dev")
        False
        >>> is_secret_path("/home/dev/.aws/config", home="/home/dev")
        True
        >>> is_secret_path("src/app/credentials.py", home="/home/dev")
        False
    """
    fold = platform in _CASE_FOLDING_PLATFORMS
    home_key = _path_key(os.path.expanduser("~") if home is None else home, platform, fold)
    key = _expand_home(_path_key(path, platform, fold), home_key)
    return _matches_any(key, SECRET_PATH_GLOBS, home_key, fold) and not _matches_any(
        key, SECRET_PATH_EXEMPT, home_key, fold
    )


def _path_key(path: str | os.PathLike[str], platform: str, fold: bool) -> str:
    """Return ``path`` as a lexically normalized, ``/``-separated comparison key."""
    text = os.fspath(path)
    if platform == "win32":
        text = text.replace("\\", "/")
    key = posixpath.normpath(text)
    return key.casefold() if fold else key


def _expand_home(key: str, home_key: str) -> str:
    """Replace a leading ``~`` in ``key`` with ``home_key``."""
    if key == "~":
        return home_key
    if key.startswith(_HOME_PREFIX):
        return posixpath.join(home_key, key[len(_HOME_PREFIX) :])
    return key


def _matches_any(key: str, globs: tuple[str, ...], home_key: str, fold: bool) -> bool:
    """Whether ``key`` matches at least one of ``globs``."""
    return any(_glob_matches(key, glob.casefold() if fold else glob, home_key) for glob in globs)


def _glob_matches(key: str, glob: str, home_key: str) -> bool:
    """Match one glob: ``~/`` globs against the home-relative path, others the final component."""
    if not glob.startswith(_HOME_PREFIX):
        return fnmatch.fnmatchcase(posixpath.basename(key), glob)
    home_relative = _relative_to_home(key, home_key)
    return home_relative is not None and fnmatch.fnmatchcase(
        home_relative, glob[len(_HOME_PREFIX) :]
    )


def _relative_to_home(key: str, home_key: str) -> str | None:
    """Return ``key`` relative to ``home_key``, or ``None`` when it lies outside it."""
    prefix = home_key.rstrip("/") + "/"
    if not key.startswith(prefix):
        return None
    return key[len(prefix) :]
