"""Git argv parsing shared by the git guards (specs/prK-lifecycle-hooks.md §D.1, §E.4).

``parse_git`` reads one parsed shell ``Segment``, so launchers (``rtk``,
``sudo``, ``env``) are already stripped and env prefixes already split out. It
finds git's global options, the subcommand, the effective cwd (``-C``, applied
cumulatively) and the runtime config that ``-c``, ``--config-env`` and
``GIT_CONFIG_COUNT`` / ``GIT_CONFIG_KEY_<n>`` / ``GIT_CONFIG_VALUE_<n>`` inject.
It matches tokens, never substrings, so ``echo git commit --no-verify`` is not
a git command. K6 and K8 build on it.

``commit_message_sources`` (specs/prK-hook-pack.md §E.4) is the message a
commit will record, read without running anything: ``-m`` values joined by a
blank line as git joins them, a ``$(cat <<EOF ... EOF)`` body, a ``-F -``
heredoc and a ``-F <file>`` inside the worktree. A process substitution, a
file outside the worktree or an editor-composed message is
:class:`Uninspectable`; the message rows then decide what that means.
"""

from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._git_options import git_args

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = [
    "MESSAGE_MAX_BYTES",
    "GitInvocation",
    "Uninspectable",
    "commit_message_sources",
    "parse_git",
]

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
#: A ``-F`` message file larger than this is not read (a message is a few lines).
MESSAGE_MAX_BYTES: Final = 64 * 1024
_MESSAGE_OPTIONS: Final = ("-m", "--message")
_FILE_OPTIONS: Final = ("-F", "--file")
#: Options that take the message from another commit or an editor template.
_REUSED_MESSAGE: Final = ("-C", "-c", "--reuse-message", "--reedit-message", "-t", "--template")


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


@dataclass(frozen=True, slots=True)
class Uninspectable:
    """The message cannot be read before the command runs; ``why`` says which source.

    Example: ``Uninspectable("-F reads a process substitution")``.
    """

    why: str


def commit_message_sources(inv: GitInvocation, *, root: str) -> list[str] | Uninspectable:
    """The message(s) ``inv`` will record, or why they cannot be read beforehand.

    ``root`` is the session's worktree root: a ``-F`` file outside it is not
    read. ``-m`` values are joined by a blank line, as git joins them.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> seg = parse_shell("git commit -m a -m b", "posix", "/r").segments[0]
        >>> commit_message_sources(parse_git(seg), root="/r")
        ['a\\n\\nb']
    """
    parsed = git_args(inv.args, inv.subcommand or "")
    messages = [_inline(value) for value in parsed.values_of(*_MESSAGE_OPTIONS)]
    found: list[str] = []
    if messages:
        if any(isinstance(m, Uninspectable) for m in messages):
            return next(m for m in messages if isinstance(m, Uninspectable))
        found.append("\n\n".join(m for m in messages if isinstance(m, str)))
    for path in parsed.values_of(*_FILE_OPTIONS):
        read = _message_file(inv, path, root)
        if isinstance(read, Uninspectable):
            return read
        found.append(read)
    if found:
        return found
    if parsed.values_of(*_REUSED_MESSAGE) or parsed.has("--amend"):
        return Uninspectable("the message is reused from another commit or a template")
    return Uninspectable("no -m or -F: an editor composes the message")


def _inline(value: str) -> str | Uninspectable:
    """One ``-m`` value: literal text, or the body of a ``$(cat <<EOF ... EOF)``."""
    if not value.startswith("$(") or not value.endswith(")"):
        return value if "$(" not in value and "`" not in value else _dynamic()
    from coding_agent_playbook.hook_runtime.shell import parse_shell

    inner = parse_shell(value[2:-1], "posix", None)
    segments = inner.segments
    if inner.parse_error is None and len(segments) == 1 and segments[0].argv == ("cat",):
        bodies = segments[0].heredoc_bodies
        if len(bodies) == 1:
            return bodies[0].rstrip("\n")
    return _dynamic()


def _dynamic() -> Uninspectable:
    return Uninspectable("the message is computed by a command substitution")


def _message_file(inv: GitInvocation, path: str, root: str) -> str | Uninspectable:
    """A ``-F`` source: stdin's heredoc for ``-`` or a small file inside ``root``."""
    if path == "-":
        bodies = inv.segment.heredoc_bodies
        return bodies[-1] if bodies else Uninspectable("-F - reads stdin")
    if path.startswith(("<(", "$", "`")) or inv.cwd is None:
        return Uninspectable("-F reads a computed path or a process substitution")
    full = os.path.realpath(os.path.join(inv.cwd, path))
    base = os.path.realpath(root)
    if os.path.commonpath([full, base]) != base:
        return Uninspectable("-F reads a file outside the worktree")
    if not os.path.isfile(full):  # a FIFO or device would block the hook
        return Uninspectable("-F names something that is not a regular file")
    try:
        with open(full, "rb") as handle:
            data = handle.read(MESSAGE_MAX_BYTES + 1)
    except OSError:
        return Uninspectable("-F names a file that cannot be read")
    if len(data) > MESSAGE_MAX_BYTES:
        return Uninspectable("-F names a file larger than a commit message")
    return data.decode("utf-8", errors="replace")
