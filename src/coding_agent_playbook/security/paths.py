"""Path-only secret classification (SPEC §17.3; specs/prK-lifecycle-hooks.md §P7, specs/prK-hook-pack.md §E.4).

:class:`PathPolicy` decides from a path string alone whether it names a
credential file, and :func:`is_secret_path` is its default instance. Neither
touches the filesystem (no ``open``, ``stat`` or symlink resolution), so a
caller can classify a path *before* deciding to read it. Normalization is
lexical only; callers that need symlink- or hard-link-aware classification
resolve the path first (§D.2.4) and pass the hard-link count as ``nlink``.
Stdlib-only: the hook dispatcher imports this module on its hot path (§D.1),
and ``security`` never imports ``hook_runtime``.

Glob grammar (``fnmatch`` syntax per path segment, case-folded on darwin/win32):

- no ``/``: matches a path's final component in any directory (``*.pem``);
- a leading ``~/``: anchored at the home directory;
- any other ``/``: anchored at the start of the key (repo-relative, or an
  absolute path for a leading ``/``).

``*`` never crosses ``/``; ``**`` matches any number of segments, and a
trailing ``/**`` matches everything below a directory but not the directory.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import sys
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from coding_agent_playbook.security.patterns import (
    SECRET_GLOB_EXEMPT,
    SECRET_PATH_EXEMPT,
    SECRET_PATH_GLOBS,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = ["DEFAULT_PATH_POLICY", "PathPolicy", "PathVerdict", "is_secret_path"]

#: Platforms whose default filesystems compare names case-insensitively.
_CASE_FOLDING_PLATFORMS: frozenset[str] = frozenset({"darwin", "win32"})

_HOME_PREFIX = "~/"
_ANY_SEGMENTS = "**"

#: ``deny`` / ``ask`` for a match; ``unknown`` for an unmatched hard link (``nlink > 1``),
#: whose other name may be a secret: only the caller's inode index can tell.
type PathVerdict = Literal["deny", "ask", "unknown"]


def _default_glob_exempt() -> Mapping[str, tuple[str, ...]]:
    return SECRET_GLOB_EXEMPT


@dataclass(frozen=True, slots=True)
class PathPolicy:
    """Secret-path globs (``deny``), exemptions (``allow``, ``glob_exempt``) and the verdict mode.

    ``allow`` cancels every deny glob; a ``glob_exempt`` entry cancels only its
    own glob (so ``*credentials*.py`` spares code but not ``.env.credentials.py``).
    The defaults are the ``security/patterns.py`` catalog. Overlays and
    consumers only append (:meth:`extended`).

    Example::

        >>> PathPolicy().classify(".env", nlink=1, home="/home/dev", platform="linux")
        'deny'
    """

    deny: tuple[str, ...] = SECRET_PATH_GLOBS
    allow: tuple[str, ...] = SECRET_PATH_EXEMPT
    glob_exempt: Mapping[str, tuple[str, ...]] = field(default_factory=_default_glob_exempt)
    mode: Literal["deny", "ask"] = "deny"

    def extended(self, *, deny: Iterable[str] = (), allow: Iterable[str] = ()) -> PathPolicy:
        """This policy with ``deny`` and ``allow`` globs appended (duplicates dropped).

        Example::

            >>> PathPolicy().extended(deny=["*.secret"]).deny[-1]
            '*.secret'
        """
        return replace(
            self,
            deny=tuple(dict.fromkeys((*self.deny, *deny))),
            allow=tuple(dict.fromkeys((*self.allow, *allow))),
        )

    def matches(
        self, path: str | os.PathLike[str], *, home: str | os.PathLike[str], platform: str
    ) -> bool:
        """Whether ``path`` matches a deny glob not cancelled for it.

        Example::

            >>> PathPolicy().matches("src/credentials.py", home="/h", platform="linux")
            False
        """
        fold = platform in _CASE_FOLDING_PLATFORMS
        home_key = _path_key(home, platform, fold)
        key = _expand_home(_path_key(path, platform, fold), home_key)
        if _matches_any(key, self.allow, home_key, fold):
            return False
        return any(
            _glob_matches(key, _folded(glob, fold), home_key)
            and not _matches_any(key, self.glob_exempt.get(glob, ()), home_key, fold)
            for glob in self.deny
        )

    def classify(
        self,
        key: str | os.PathLike[str],
        *,
        nlink: int = 1,
        home: str | os.PathLike[str],
        platform: str = sys.platform,
    ) -> PathVerdict | None:
        """``mode`` for a secret ``key``, ``"unknown"`` for an unmatched hard link, else ``None``.

        ``key`` is a normalized path (``NormalizedPath.key`` in the hook
        runtime); ``nlink`` its hard-link count. A hard link is not asked
        about on its own: uv's hard-linked ``.venv`` installs would ask on
        every read, so the caller consults its secret-inode index.

        Example::

            >>> PathPolicy().classify("notes.txt", nlink=2, home="/h", platform="linux")
            'unknown'
        """
        if self.matches(key, home=home, platform=platform):
            return self.mode
        return "unknown" if nlink > 1 else None


#: The engine catalog as a policy; :func:`is_secret_path` and the detector use it.
DEFAULT_PATH_POLICY = PathPolicy()


def is_secret_path(
    path: str | os.PathLike[str],
    *,
    home: str | os.PathLike[str],
    platform: str = sys.platform,
) -> bool:
    """Whether ``path`` names a credential file the engine must never read.

    The :data:`DEFAULT_PATH_POLICY` match. ``home`` is required: it anchors
    the ``~/`` globs and expands a leading ``~`` in ``path``, and each caller
    states whose home that is (the current user's for the detector; the hook
    runtime passes its own). ``platform`` selects case folding (darwin,
    win32) and ``\\`` separators (win32); it defaults to ``sys.platform``
    and is injectable for tests.

    Example::

        >>> is_secret_path("deploy/.env", home="/home/dev")
        True
        >>> is_secret_path(".env.example", home="/home/dev")
        False
        >>> is_secret_path("/home/dev/.aws/config", home="/home/dev")
        True
        >>> is_secret_path("src/app/credentials.py", home="/home/dev")
        False
        >>> is_secret_path(".env.credentials.py", home="/home/dev")
        True
    """
    return DEFAULT_PATH_POLICY.matches(path, home=home, platform=platform)


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


def _matches_any(key: str, globs: Iterable[str], home_key: str, fold: bool) -> bool:
    """Whether ``key`` matches at least one of ``globs``."""
    return any(_glob_matches(key, _folded(glob, fold), home_key) for glob in globs)


def _folded(glob: str, fold: bool) -> str:
    """``glob`` case-folded on a case-insensitive platform, else unchanged."""
    return glob.casefold() if fold else glob


def _glob_matches(key: str, glob: str, home_key: str) -> bool:
    """Match one glob in its shape: basename, home-anchored or key-anchored."""
    if glob.startswith(_HOME_PREFIX):
        home_relative = _relative_to_home(key, home_key)
        return home_relative is not None and _segments_match(
            home_relative.split("/"), glob[len(_HOME_PREFIX) :].split("/")
        )
    if "/" not in glob:
        return fnmatch.fnmatchcase(posixpath.basename(key), glob)
    return _segments_match(key.split("/"), glob.split("/"))


def _segments_match(parts: Sequence[str], pattern: Sequence[str]) -> bool:
    """Segment-wise ``fnmatch``: ``**`` spans segments (one or more when it ends the glob)."""
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == _ANY_SEGMENTS:
        if not rest:
            return bool(parts)
        return any(_segments_match(parts[i:], rest) for i in range(len(parts) + 1))
    return bool(parts) and fnmatch.fnmatchcase(parts[0], head) and _segments_match(parts[1:], rest)


def _relative_to_home(key: str, home_key: str) -> str | None:
    """Return ``key`` relative to ``home_key``, or ``None`` when it lies outside it."""
    prefix = home_key.rstrip("/") + "/"
    if not key.startswith(prefix):
        return None
    return key[len(prefix) :]
