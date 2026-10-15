"""``SafeGit``'s two discovery caches: git's version and its filter drivers (§D.5.3).

Both live under ``<state>/cache`` so a hook process usually spawns no git just
to learn how to call git safely.

- ``cache/git-version`` is keyed by the git executable's path and stat
  signature, so an upgraded git is re-asked.
- ``cache/git-filters.json`` is keyed by the stat of every config file git
  read for the answer: the repo, worktree and global files (§D.5.3), plus every
  file that defined a filter or an include, plus every include target. Keying
  on include targets matters: an agent that adds ``[include] path = x.cfg``
  and later writes a filter into ``x.cfg`` must invalidate the cache, or that
  filter would run unneutralized.

The discovery reads only key names and include paths, never other values, so
no credential stored in a config value passes through the runtime.
"""

from __future__ import annotations

import os
import re
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._git_parse import parse_version
from coding_agent_playbook.hook_runtime.git import GitError
from coding_agent_playbook.hook_runtime.state import StateUnavailable

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.git import SafeGit

__all__ = ["cached_version", "filter_flags"]

VERSION_CACHE: Final = "cache/git-version"
FILTER_CACHE: Final = "cache/git-filters.json"
_DISCOVERY_PATTERN: Final = r"^(filter\..*|include\.path|includeif\..*\.path)$"
#: A subsection a ``-c filter.<name>.<var>=`` argument can carry unambiguously.
_SAFE_NAME = re.compile(r"[^=\s\x00-\x1f]+")
_FILE_ORIGIN: Final = "file:"

type Signature = list[int] | None


def cached_version(git: SafeGit) -> tuple[int, int, int]:
    """git's ``(major, minor, patch)``; raises ``GitError`` when unrecognizable.

    Example::

        >>> cached_version(git)  # doctest: +SKIP
        (2, 39, 3)
    """
    executable = git.executable()
    signature = _signature(executable)
    key = [executable, signature]
    cached = _read(git, VERSION_CACHE)
    if signature is not None and cached.get("key") == key:
        version = _as_version(cached.get("version"))
        if version is not None:
            return version
    parsed = parse_version(git.bare_run(["--version"]).stdout)
    if parsed is None:
        raise GitError("git --version printed no recognizable version")
    if signature is not None:  # an unstattable git cannot be keyed: ask every time
        _write(git, VERSION_CACHE, {"key": key, "version": list(parsed)})
    return parsed


def filter_flags(git: SafeGit) -> tuple[str, ...]:
    """The ``-c`` arguments that neutralize every configured filter driver.

    Example::

        >>> filter_flags(git)  # doctest: +SKIP
        ('-c', 'filter.lfs.clean=', '-c', 'filter.lfs.smudge=', ...)
    """
    return tuple(arg for name in _filter_names(git) for arg in _neutralize(name))


def _filter_names(git: SafeGit) -> list[str]:
    cached = _read(git, FILTER_CACHE)
    if _cache_valid(git, cached):
        return [name for name in cached["filters"] if isinstance(name, str)]
    # Signed before git reads them: a file edited during discovery then
    # mismatches its stored signature, so the next call discovers again.
    before = {path: _signature(path) for path in _base_files(git)}
    result = git.bare_run(
        ["config", "--null", "--show-origin", "--get-regexp", _DISCOVERY_PATTERN], ok_codes=(0, 1)
    )
    names, files = _parse_discovery(git, result.stdout)
    signed = [[p, before[p] if p in before else _signature(p)] for p in sorted({*before, *files})]
    _write(git, FILTER_CACHE, {"files": signed, "filters": sorted(names)})
    return sorted(names)


def _neutralize(name: str) -> tuple[str, ...]:
    if not _SAFE_NAME.fullmatch(name):
        raise GitError(f"filter driver {name!r} cannot be neutralized on the command line")
    return tuple(
        arg
        for var, value in (("clean", ""), ("smudge", ""), ("process", ""), ("required", "false"))
        for arg in ("-c", f"filter.{name}.{var}={value}")
    )


def _parse_discovery(git: SafeGit, output: bytes) -> tuple[set[str], set[str]]:
    """Filter names, plus every origin file and include target the listing named."""
    tokens = output.split(b"\x00")
    names: set[str] = set()
    files: set[str] = set()
    for origin_raw, entry in zip(tokens[0::2], tokens[1::2], strict=False):
        origin = _origin_file(git, origin_raw.decode("utf-8", "surrogateescape"))
        key, _, value = entry.decode("utf-8", "surrogateescape").partition("\n")
        if origin is not None:
            files.add(origin)
        if key.startswith("filter.") and key.count(".") >= 2:
            names.add(key[len("filter.") : key.rindex(".")])
        elif key.endswith(".path") and value:
            files.add(_include_target(git, value, origin))
    return names, files


def _origin_file(git: SafeGit, origin: str) -> str | None:
    if not origin.startswith(_FILE_ORIGIN):
        return None  # "command line:" etc.: nothing on disk to watch
    return os.path.normpath(os.path.join(git.repo.worktree_root, origin[len(_FILE_ORIGIN) :]))


def _include_target(git: SafeGit, value: str, origin: str | None) -> str:
    if value.startswith("~/"):
        value = os.path.join(git.env.get("HOME", "~"), value[2:])
    base = os.path.dirname(origin) if origin else git.repo.worktree_root
    return os.path.normpath(os.path.join(base, value))


def _base_files(git: SafeGit) -> list[str]:
    """The config files git reads even when they are absent today (§D.5.3)."""
    env, repo = git.env, git.repo
    files = [os.path.join(repo.common_dir, "config"), os.path.join(repo.git_dir, "config.worktree")]
    home = env.get("HOME", "")
    if env.get("GIT_CONFIG_GLOBAL"):
        files.append(env["GIT_CONFIG_GLOBAL"])
    else:
        xdg = env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
        files += [os.path.join(xdg, "git", "config"), os.path.join(home, ".gitconfig")]
    if env.get("GIT_CONFIG_SYSTEM") and not env.get("GIT_CONFIG_NOSYSTEM"):
        files.append(env["GIT_CONFIG_SYSTEM"])
    return [os.path.normpath(f) for f in files]


def _cache_valid(git: SafeGit, cached: dict[str, Any]) -> bool:
    signed = cached.get("files")
    if not isinstance(signed, list) or not isinstance(cached.get("filters"), list):
        return False
    pairs = [p for p in signed if isinstance(p, list) and len(p) == 2 and isinstance(p[0], str)]
    if len(pairs) != len(signed) or not set(_base_files(git)) <= {p[0] for p in pairs}:
        return False
    return all(_signature(path) == sig for path, sig in pairs)


def _signature(path: str) -> Signature:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return [info.st_mtime_ns, info.st_size, info.st_ino]


def _as_version(value: object) -> tuple[int, int, int] | None:
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) for v in value):
        return (value[0], value[1], value[2])
    return None


def _read(git: SafeGit, rel: str) -> dict[str, Any]:
    if git.state is None:
        return {}
    try:
        return git.state.read_json(rel)
    except StateUnavailable:
        return {}


def _write(git: SafeGit, rel: str, document: dict[str, Any]) -> None:
    if git.state is None:
        return
    with suppress(StateUnavailable):  # stateless: discover again next process
        git.state.write_json(rel, document)
