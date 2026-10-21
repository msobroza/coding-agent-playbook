"""Shell commands that print a forge token (specs/prF-forge-adapter.md §14, Q64).

``gh``, ``glab`` and ``playbook forge`` use the forge CLIs' own login, so the
agent never needs a token's value, and one printed into the transcript has
left the machine (it reaches the model endpoint). :func:`token_print` names
the first command of a parsed command line that prints a forge token:

- a forge CLI command in its forge's ``token_printers`` (``gh auth token``,
  ``glab auth status -t``, ``glab config get token``; ``forge.tokens``);
- ``printenv NAME`` and ``echo`` / ``printf`` of ``$NAME`` / ``${NAME}`` for a
  name in any forge's ``token_env`` (``GH_TOKEN``, ``GITLAB_TOKEN``, ...); a
  single-quoted ``'$GH_TOKEN'``, ``${#GH_TOKEN}`` (its length) and
  ``${GH_TOKEN:+set}`` print no token and pass;
- a bare ``env`` / ``printenv`` piped into a filter naming such a variable,
  or part of one (``printenv | grep GH_TOKEN``, ``env | grep -i token``).

Offline and pure, like :mod:`~coding_agent_playbook.hook_runtime.judges.forge_calls`:
the forge tables load for a forge CLI's segment, or a word that holds
``TOKEN`` or follows an environment dump, only.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.judges.cli_words import split_words
from coding_agent_playbook.hook_runtime.judges.forge_calls import FORGE_ARGV0S

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.forge.dialects import Forge
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["TOKEN_PRINT_ARGV0S", "token_print"]

_ECHOES: Final = frozenset({"echo", "printf"})
_PRINTENV: Final = "printenv"
#: The environment dumps a pipe may filter down to a token.
_DUMPS: Final = frozenset({"env", _PRINTENV})
#: The programs :func:`token_print` reads by name, beside the forge CLIs.
TOKEN_PRINT_ARGV0S: Final = (*sorted(_DUMPS), *sorted(_ECHOES))
#: Every forge token env var name holds it, so a word without it loads no table.
_TOKEN: Final = "TOKEN"
#: ``$NAME`` or ``${NAME...}``; ``${NAME:+x}`` / ``${NAME+x}`` print ``x``, never the value,
#: and ``${#NAME}`` (a length) or ``${!NAME}`` match no name here.
_EXPANSION: Final = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)(:?\+)?|([A-Za-z_][A-Za-z0-9_]*))")
#: The shortest filter word read as part of a token name (``grep -i token``).
_MIN_PART: Final = 4
_NON_NAME: Final = re.compile(r"[^A-Z0-9_]+")


def token_print(segments: Sequence[Segment], *, degraded: bool = False) -> str | None:
    """The first command of ``segments`` that prints a forge token, as shown to the model.

    ``degraded``: the words come from a regex split, so any word may expand.

    Example::

        >>> token_print(parse_shell("echo $GH_TOKEN", "posix", "/r").segments)
        ... # doctest: +SKIP
        'echo $GH_TOKEN'
    """
    for index, segment in enumerate(segments):
        shown = _segment(segment, degraded=degraded) or _filtered_dump(segments, index)
        if shown is not None:
            return shown
    return None


def _segment(segment: Segment, *, degraded: bool) -> str | None:
    argv = segment.argv
    if not argv or 0 in segment.dynamic:
        return None
    program = _program(argv[0])
    if program == _PRINTENV:
        hit = _token_name(word for word in argv[1:] if not word.startswith("-"))
        return None if hit is None else f"{_PRINTENV} {hit}"
    if program in _ECHOES:
        words = (w for i, w in enumerate(argv) if i and (degraded or i in segment.dynamic))
        hit = _token_name(name for word in words for name in _expanded(word))
        return None if hit is None else f"{program} ${hit}"
    if program not in FORGE_ARGV0S:
        return None
    from coding_agent_playbook.forge.dialects import by_cli

    forge = by_cli(program)
    return None if forge is None else _cli(forge, argv[1:])


def _cli(forge: Forge, words: Sequence[str]) -> str | None:
    for printer in forge.token_printers:
        parsed = split_words(words, printer.values)
        operands = parsed.operands
        if tuple(operands[: len(printer.path)]) != printer.path:
            continue
        shown = " ".join((forge.cli, *printer.path))
        operand = operands[len(printer.path) : len(printer.path) + 1]
        if printer.operands:
            if operand and operand[0].lower() in printer.operands:
                return f"{shown} {operand[0]}"
        elif not printer.flags:
            return shown
        elif parsed.given(printer.flags):
            return f"{shown} {max(sorted(printer.flags), key=len)}"
    return None


def _filtered_dump(segments: Sequence[Segment], index: int) -> str | None:
    """``env | grep GH_TOKEN``: a bare dump piped into a filter naming a token variable."""
    dump = segments[index]
    argv = dump.argv
    if not dump.pipes_to_next or not argv or _program(argv[0]) not in _DUMPS:
        return None
    if any(not word.startswith("-") for word in argv[1:]):
        return None  # env running a command, or printenv of named variables
    for segment in segments[index + 1 :]:
        words = [w for w in segment.argv[1:] if not w.startswith("-")]
        part = next((w for w in words if _names_token(w)), None)
        if part is not None:
            return f"{_program(argv[0])} | {_program(segment.argv[0])} {part}"
        if not segment.pipes_to_next:
            break
    return None


def _names_token(word: str) -> bool:
    """Whether a filter word holds a forge token variable's name, or a part of one.

    A pattern's alternatives count one by one (``grep -E 'GITLAB|PATH'``).
    """
    names = _token_names()
    parts = [p for p in _NON_NAME.split(word.upper()) if len(p) >= _MIN_PART]
    return any(n in part or part in n for part in parts for n in names)


def _expanded(word: str) -> Iterable[str]:
    """The variables ``word`` expands to their value."""
    for braced, alternate, bare in _EXPANSION.findall(word):
        if braced and not alternate:
            yield braced
        elif bare:
            yield bare


def _token_name(names: Iterable[str]) -> str | None:
    """The first of ``names`` that is a forge's token env var."""
    candidates = [name for name in names if _TOKEN in name]
    if not candidates:
        return None
    tokens = _token_names()
    return next((name for name in candidates if name in tokens), None)


def _token_names() -> frozenset[str]:
    from coding_agent_playbook.forge.dialects import FORGES

    return frozenset(name for forge in FORGES for name in forge.token_env)


def _program(argv0: str) -> str:
    return posixpath.basename(argv0).removesuffix(".exe")
