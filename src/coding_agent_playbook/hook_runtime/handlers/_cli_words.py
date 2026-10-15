"""A command's words split the way a typical CLI reads them (specs/prK-hook-pack.md §E.4).

The install parser (``_install_cmds``) and the egress classifier (``_egress``)
read pip, uv, npm, curl, wget, scp and friends, whose option grammars agree on
the basics: ``--name=value``; ``--name value`` and ``-x value`` when the option
takes a value (the caller's table); ``-xvalue`` for a short one; ``--`` ends
the options; ``-`` alone is an operand (stdin). An option the table does not
know is a flag, so an unknown value option makes its value look like an
operand: the conservative direction for a guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["CliWords", "split_words", "value_options"]


@dataclass(slots=True)
class CliWords:
    """The option values, flags and operands of one command, in order.

    Example::

        >>> words = split_words(["-r", "req.txt", "--pre", "rich"], value_options("-r"))
        >>> words.of(value_options("-r")), sorted(words.flags), words.operands
        (['req.txt'], ['--pre'], ['rich'])
    """

    values: list[tuple[str, str]] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    operands: list[str] = field(default_factory=list)

    def of(self, options: frozenset[str]) -> list[str]:
        """Every value given to one of ``options``, in order."""
        return [value for option, value in self.values if option in options]


def value_options(text: str) -> frozenset[str]:
    """A CLI's value-taking options, from a space-separated list.

    Example::

        >>> sorted(value_options("-r --requirement"))
        ['--requirement', '-r']
    """
    return frozenset(text.split())


def split_words(
    words: Sequence[str], values: frozenset[str], *, stop_at_operand: bool = False
) -> CliWords:
    """Split ``words``; ``stop_at_operand``: the first operand ends the options (a runner's).

    Example::

        >>> split_words(["--from", "x", "tool", "--flag"], value_options("--from"),
        ...             stop_at_operand=True).operands
        ['tool', '--flag']
    """
    found = CliWords()
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--" or (stop_at_operand and found.operands):
            found.operands.extend(words[index + (word == "--") :])
            break
        if word.startswith("-") and word != "-":
            index = _option(words, index, values, found)
            continue
        found.operands.append(word)
        index += 1
    return found


def _option(words: Sequence[str], index: int, values: frozenset[str], found: CliWords) -> int:
    word = words[index]
    name, glued, value = word.partition("=")
    if word.startswith("--") and glued:
        found.values.append((name, value))
        return index + 1
    if word in values:
        if index + 1 < len(words):
            found.values.append((word, words[index + 1]))
        return index + 2
    if not word.startswith("--") and word[:2] in values and len(word) > 2:
        found.values.append((word[:2], word[2:]))  # pip's -rrequirements.txt, curl's -d@f
        return index + 1
    found.flags.add(word)
    return index + 1
