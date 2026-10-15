"""Git argv parsing shared by the git guards (specs/prK-lifecycle-hooks.md §D.1, §E.4).

``parse_git`` reads one parsed shell ``Segment``, so launchers (``rtk``,
``sudo``, ``env``) are already stripped and env prefixes already split out. It
finds git's global options, the subcommand, the effective cwd (``-C``, applied
cumulatively) and the runtime config that ``-c``, ``--config-env`` and
``GIT_CONFIG_COUNT`` / ``GIT_CONFIG_KEY_<n>`` / ``GIT_CONFIG_VALUE_<n>`` inject.
It matches tokens, never substrings, so ``echo git commit --no-verify`` is not
a git command. K6 and K8 build on it (``commit_message_sources``, ...).
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["GitInvocation", "parse_git"]

_GIT_NAMES = frozenset({"git", "git.exe"})
#: Global options whose value is the next word unless glued with ``=``.
_WITH_VALUE = frozenset(
    {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--config-env",
        "--super-prefix",
        "--list-cmds",
        "--attr-source",
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class GitInvocation:
    """One ``git`` command as git itself would read its argv.

    ``config`` lists ``(name, value)`` pairs in the order git applies them
    (env first, then ``-c``), so the last one wins; ``-c name`` with no ``=``
    means ``true``. ``cwd`` is the segment cwd with every ``-C`` applied
    (``None`` = unknown).

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> segment = parse_shell("git -C sub push", "posix", "/r").segments[0]
        >>> invocation = parse_git(segment)
        >>> (invocation.subcommand, invocation.cwd)
        ('push', '/r/sub')
    """

    subcommand: str | None
    args: tuple[str, ...]
    global_args: tuple[str, ...]
    config: tuple[tuple[str, str], ...]
    cwd: str | None
    git_dir: str | None = None
    work_tree: str | None = None
    segment: Segment = field(repr=False)

    def config_value(self, name: str) -> str | None:
        """The effective value of config ``name`` (compared case-insensitively), else None."""
        wanted = name.lower()
        for key, value in reversed(self.config):
            if key.lower() == wanted:
                return value
        return None


@dataclass(slots=True)
class _Globals:
    """What git's global options set, accumulated left to right."""

    cwd: str | None
    config: list[tuple[str, str]]
    git_dir: str | None
    work_tree: str | None


def parse_git(segment: Segment) -> GitInvocation | None:
    """The git invocation ``segment`` runs, or ``None`` when its command is not git.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> parse_git(parse_shell("ls", "posix", "/r").segments[0]) is None
        True
    """
    argv = segment.argv
    if not argv or 0 in segment.dynamic or posixpath.basename(argv[0]) not in _GIT_NAMES:
        return None
    env = dict(segment.env)
    found = _Globals(segment.cwd, _env_config(env), env.get("GIT_DIR"), env.get("GIT_WORK_TREE"))
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        option, value, value_index, index = _option_at(argv, index)
        _apply(found, option, value, env, dynamic=value_index in segment.dynamic)
    return GitInvocation(
        subcommand=argv[index] if index < len(argv) else None,
        args=argv[index + 1 :],
        global_args=argv[1:index],
        config=tuple(found.config),
        cwd=found.cwd,
        git_dir=found.git_dir,
        work_tree=found.work_tree,
        segment=segment,
    )


def _env_config(env: Mapping[str, str]) -> list[tuple[str, str]]:
    """The ``GIT_CONFIG_COUNT`` pairs; git rejects a missing key, so reading stops there."""
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        return []
    pairs: list[tuple[str, str]] = []
    for number in range(count):
        key = env.get(f"GIT_CONFIG_KEY_{number}")
        if key is None:
            break
        pairs.append((key, env.get(f"GIT_CONFIG_VALUE_{number}", "")))
    return pairs


def _option_at(argv: tuple[str, ...], index: int) -> tuple[str, str | None, int, int]:
    """``(option, value, value_index, next_index)`` for the global option at ``index``."""
    token = argv[index]
    if token.startswith("--") and "=" in token:
        option, _, value = token.partition("=")
        return option, value, index, index + 1
    if token in _WITH_VALUE and index + 1 < len(argv):
        return token, argv[index + 1], index + 1, index + 2
    return token, None, -1, index + 1


def _apply(
    found: _Globals, option: str, value: str | None, env: Mapping[str, str], *, dynamic: bool
) -> None:
    if value is None:
        return
    if option == "-C":
        found.cwd = _change_dir(found.cwd, value, dynamic=dynamic)
    elif option == "-c":
        name, has_value, assigned = value.partition("=")
        found.config.append((name, assigned if has_value else "true"))
    elif option == "--config-env":
        name, _, variable = value.partition("=")
        found.config.append((name, env.get(variable, f"${variable}")))
    elif option == "--git-dir":
        found.git_dir = value
    elif option == "--work-tree":
        found.work_tree = value


def _change_dir(cwd: str | None, path: str, *, dynamic: bool) -> str | None:
    """Apply one ``-C path``: relative to the previous cwd; an empty path is a no-op."""
    if dynamic:
        return None
    if not path:
        return cwd
    if path.startswith("/"):
        return posixpath.normpath(path)
    return None if cwd is None else posixpath.normpath(posixpath.join(cwd, path))
