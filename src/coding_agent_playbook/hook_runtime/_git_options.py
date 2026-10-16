"""A git subcommand's own options, read the way git reads them (specs/prK-hook-pack.md §E.2, §E.4).

``parse_git`` stops at the subcommand; the git guards (block-precommit-bypass,
destructive-command-guard, git-commit-push-policy-guard) then need the
subcommand's flags, the values of its value-taking options and its operands.
One parser serves them all, so ``-m "fix -n handling"`` is a message to every
guard and never a ``-n`` flag:

- a long option takes the next word when it is in :data:`VALUE_LONGS` and has
  no ``=``; a short cluster stops at its first value letter
  (:data:`VALUE_SHORTS`): the rest of the cluster (``-mfoo``) or, when the
  letter is last (``-am x``), the next word is its value;
- operands after ``--`` are pathspecs, kept apart from the positionals.

``config_words`` is ``git config``'s key and value words, ``None`` for a read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["VALUE_LONGS", "VALUE_SHORTS", "GitArgs", "config_words", "git_args"]

#: Short options that take a value, per subcommand: the value is data, not flags.
VALUE_SHORTS: Final = {
    "commit": frozenset("mFCct"),
    "merge": frozenset("mFsX"),
    "rebase": frozenset("sxX"),
    "cherry-pick": frozenset("mX"),
    "push": frozenset("o"),
    "tag": frozenset("mFu"),
    "stash": frozenset("m"),
    "clean": frozenset("e"),
    "branch": frozenset("u"),
}
#: Long options that take the next word as their value (when not glued with ``=``).
VALUE_LONGS: Final = frozenset(
    {
        "--message",
        "--file",
        "--reuse-message",
        "--reedit-message",
        "--author",
        "--date",
        "--template",
        "--cleanup",
        "--fixup",
        "--squash",
        "--trailer",
        "--pathspec-from-file",
        "--strategy",
        "--strategy-option",
        "--exec",
        "--onto",
        "--push-option",
        "--repo",
        "--mainline",
        "--receive-pack",
        "--local-user",
        "--exclude",
        "--set-upstream-to",
    }
)
_CONFIG_READS: Final = frozenset(
    {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "get", "list"}
)
_CONFIG_VERBS: Final = frozenset(
    {"set", "unset", "--unset", "--unset-all", "--add", "--replace-all"}
)
#: ``git config`` options whose value is the next word (``--file .git/config``).
_CONFIG_VALUE_OPTIONS: Final = frozenset(
    {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value"}
)


@dataclass(frozen=True, slots=True)
class GitArgs:
    """One subcommand's arguments, split as git splits them.

    ``flags`` holds long option names (``--force``, ``--message``) and short
    letters; ``values`` each value option with its value, in order;
    ``positionals`` the operands before ``--`` and ``pathspecs`` those after.

    Example::

        >>> parsed = git_args(["-am", "fix -n", "--", "a.py"], "commit")
        >>> sorted(parsed.flags), parsed.values, parsed.pathspecs
        (['a', 'm'], (('-m', 'fix -n'),), ('a.py',))
    """

    flags: frozenset[str]
    values: tuple[tuple[str, str], ...]
    positionals: tuple[str, ...]
    pathspecs: tuple[str, ...]

    def has(self, *names: str) -> bool:
        """Whether any of ``names`` (``--long`` or a single short letter) was given."""
        return any(name in self.flags for name in names)

    def values_of(self, *options: str) -> list[str]:
        """Every value given to one of ``options`` (``-m``, ``--message``), in order."""
        return [value for option, value in self.values if option in options]

    @property
    def longs(self) -> frozenset[str]:
        """The ``--long`` option names alone."""
        return frozenset(flag for flag in self.flags if flag.startswith("--"))

    @property
    def shorts(self) -> frozenset[str]:
        """The short option letters alone."""
        return frozenset(flag for flag in self.flags if not flag.startswith("--"))


def git_args(args: Sequence[str], sub: str) -> GitArgs:
    """Split subcommand ``sub``'s ``args`` into flags, option values and operands.

    Example::

        >>> git_args(["push", "--force", "origin", "main"][1:], "push").positionals
        ('origin', 'main')
    """
    shorts = VALUE_SHORTS.get(sub, frozenset())
    flags: set[str] = set()
    values: list[tuple[str, str]] = []
    positionals: list[str] = []
    index = 0
    while index < len(args) and args[index] != "--":
        arg = args[index]
        if arg.startswith("--"):
            index = _long(args, index, flags, values)
        elif arg.startswith("-") and len(arg) > 1:
            index = _short(args, index, shorts, flags, values)
        else:
            positionals.append(arg)
            index += 1
    return GitArgs(frozenset(flags), tuple(values), tuple(positionals), tuple(args[index + 1 :]))


def config_words(args: Sequence[str]) -> list[str] | None:
    """``git config``'s key and value words (options and verbs dropped); ``None`` for a read.

    Example::

        >>> config_words(["--global", "user.email", "a@b"]), config_words(["--get", "user.name"])
        (['user.email', 'a@b'], None)
    """
    if any(arg in _CONFIG_READS for arg in args):
        return None
    words: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
        elif arg in _CONFIG_VALUE_OPTIONS:
            skip_next = True
        elif not arg.startswith("-") and arg not in _CONFIG_VERBS:
            words.append(arg)
    return words


def _long(args: Sequence[str], index: int, flags: set[str], values: list[tuple[str, str]]) -> int:
    name, glued, value = args[index].partition("=")
    flags.add(name)
    if glued:
        values.append((name, value))
        return index + 1
    if name in VALUE_LONGS and index + 1 < len(args):
        values.append((name, args[index + 1]))
        return index + 2
    return index + 1


def _short(
    args: Sequence[str],
    index: int,
    value_shorts: frozenset[str],
    flags: set[str],
    values: list[tuple[str, str]],
) -> int:
    """One ``-abc`` cluster: letters up to the first one taking a value (module docstring)."""
    text = args[index][1:]
    for position, letter in enumerate(text):
        flags.add(letter)
        if letter not in value_shorts:
            continue
        rest = text[position + 1 :]
        if rest:
            values.append((f"-{letter}", rest))
            return index + 1
        if index + 1 < len(args):
            values.append((f"-{letter}", args[index + 1]))
            return index + 2
        return index + 1
    return index + 1
