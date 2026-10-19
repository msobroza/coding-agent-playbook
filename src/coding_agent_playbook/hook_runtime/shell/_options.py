"""Command-line option reading shared by unwrapping and ``write_targets`` (§D.2.5).

Launchers (``sudo -u root rm``) and writers (``cp -t DIR``) are both read by
skipping options correctly: a short letter that takes an argument consumes the
rest of its cluster or the next word, and a long option consumes the next word
unless it is glued with ``=``. One ``OptionSpec`` per command says which.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.shell.tokens import Word

_ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """How one command's options read.

    ``with_arg`` lists the short letters that take an argument (glued, or the
    next word) and ``long_with_arg`` the long options that do. ``assignments``
    sends ``NAME=V`` operands to the env (``env``, ``sudo``); ``positional``
    counts operands consumed before the wrapped command (``timeout``'s
    DURATION); ``plus`` accepts ``+o``-style options (shells).

    Example: ``OptionSpec("u", long_names("user"), assignments=True)``.
    """

    with_arg: str = ""
    long_with_arg: frozenset[str] = frozenset()
    assignments: bool = False
    positional: int = 0
    plus: bool = False


def long_names(names: str) -> frozenset[str]:
    """``"user chdir"`` as ``{"--user", "--chdir"}``.

    Example::

        >>> sorted(long_names("user chdir"))
        ['--chdir', '--user']
    """
    return frozenset(f"--{name}" for name in names.split())


def option_arity(token: str, spec: OptionSpec) -> int:
    """How many following words the option ``token`` consumes (0 or 1).

    Example::

        >>> option_arity("-Eu", OptionSpec(with_arg="u")), option_arity("-uroot", OptionSpec("u"))
        (1, 0)
    """
    if token.startswith("--"):
        return int("=" not in token and token in spec.long_with_arg)
    for offset, letter in enumerate(token[1:], 1):
        if letter in spec.with_arg:
            return int(offset == len(token) - 1)
    return 0


def skip_options(
    argv: list[Word], index: int, spec: OptionSpec
) -> tuple[int, list[tuple[str, str]]]:
    """Skip the leading options at ``index``: ``(command index, NAME=V assignments)``.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell.tokens import Word
        >>> words = [Word(v) for v in ("sudo", "-u", "root", "rm")]
        >>> skip_options(words, 1, OptionSpec("u"))
        (3, [])
    """
    env: list[tuple[str, str]] = []
    while index < len(argv):
        value = argv[index].value
        if value == "--":
            index += 1
            break
        if spec.assignments and _ENV_ASSIGNMENT.match(value):
            name, _, assigned = value.partition("=")
            env.append((name, assigned))
            index += 1
        elif len(value) > 1 and (value[0] == "-" or (spec.plus and value[0] == "+")):
            index += 1 + option_arity(value, spec)
        else:
            break
    return index + spec.positional, env


def has_letter(tokens: list[Word], letters: str, longs: tuple[str, ...] = ()) -> bool:
    """Whether a short-option cluster in ``tokens`` holds one of ``letters``, or a ``longs`` option.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell.tokens import Word
        >>> has_letter([Word("-lc")], "c")
        True
    """
    for token in tokens:
        value = token.value
        if value in longs:
            return True
        if value[:1] == "-" and value[:2] != "--" and set(value[1:]) & set(letters):
            return True
    return False
