"""The argv and env rules every ``SafeGit`` call follows (specs/prK-lifecycle-hooks.md §D.5.3).

Split from ``safe_git.py`` to keep both under §D.1's 300-line module rule; pure
helpers only. The scrubbed variables are a superset of §D.5.3's list: on top
of the config-injecting ones, every variable that relocates the repository or
its object store is dropped, because each ``SafeGit`` call runs at the
worktree root and must find exactly that repository.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["FSMONITOR", "child_env", "first_line", "subcommand", "with_diff_flags"]

FSMONITOR: Final = ("-c", "core.fsmonitor=false")
_DIFF_COMMANDS: Final = frozenset({"diff", "log", "show"})
_DIFF_FLAGS: Final = ("--no-ext-diff", "--no-textconv")
#: Variables that relocate the repository or inject config; a superset of §D.5.3's list.
_SCRUBBED: Final = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_EXTERNAL_DIFF",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_ATTR_SOURCE",
    }
)
_SCRUBBED_PREFIXES: Final = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
_FORCED_ENV: Final = {
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PAGER": "cat",
    "LC_ALL": "C",
}


def child_env(env: Mapping[str, str]) -> dict[str, str]:
    """``env`` without the repo-relocating and config-injecting git variables.

    Example::

        >>> child_env({"GIT_DIR": "/evil", "HOME": "/h"})["HOME"], "GIT_DIR" in child_env({})
        ('/h', False)
    """
    kept = {
        name: value
        for name, value in env.items()
        if name not in _SCRUBBED and not name.startswith(_SCRUBBED_PREFIXES)
    }
    return {**kept, **_FORCED_ENV}


def with_diff_flags(args: Sequence[str]) -> list[str]:
    """``args`` with ``--no-ext-diff --no-textconv`` after a diff/log/show subcommand.

    Example::

        >>> with_diff_flags(["diff", "HEAD"])
        ['diff', '--no-ext-diff', '--no-textconv', 'HEAD']
    """
    command = list(args)
    if command and command[0] in _DIFF_COMMANDS:
        command[1:1] = _DIFF_FLAGS
    return command


def subcommand(args: Sequence[str]) -> str:
    """The first argument that is not a ``-c key=value`` pair, for error messages.

    Example::

        >>> subcommand(["-c", "core.fsmonitor=false", "status"])
        'status'
    """
    index = 0
    while index < len(args) and args[index] == "-c":
        index += 2
    return args[index] if index < len(args) else "<none>"


def first_line(stderr: bytes) -> str:
    """The first line of a child's stderr, for an error message.

    Example::

        >>> first_line(b"fatal: bad index\\nmore\\n")
        'fatal: bad index'
    """
    text = stderr.decode("utf-8", errors="replace").strip()
    return text.splitlines()[0] if text else "(no stderr)"
