"""The arguments of one ``playbook forge`` operation, read against its catalogue row (spec prF §6.1).

:func:`parse_call` finds the operation the words name
(:func:`coding_agent_playbook.forge.operations.operation_call`, the reading the
guards share) and checks its arguments against the operation's row: its
positionals in order, value options (``--opt v`` or ``--opt=v``), flags,
repeatable options and closed choices, plus ``--json`` anywhere. The body
(Q36) comes from ``--body TEXT``, ``--body-file PATH``, ``--body-file -``
(stdin) or ``--template PATH`` (a body file, Q56) and is read here, once. A
usage error exits 1: the agent reads it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._forge_stop import ForgeStop
from coding_agent_playbook.forge.operations import BODY_FILE, OPERATIONS, TEMPLATE, operation_call

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.forge.operations import Operation

__all__ = ["Call", "operation_help", "operations_help", "parse_call"]

_BODY: Final = "--body"
_JSON: Final = "--json"
_STDIN: Final = "-"
#: Positionals passed as written: a reference keeps ``#`` / ``!``, a label name is text.
_VERBATIM: Final = frozenset({"ref", "name"})
_NUMBERED: Final = re.compile(r"[#!]\d+")


@dataclass(frozen=True)
class Call:
    """One parsed ``playbook forge`` operation: its positionals, options, flags and body.

    ``options`` maps each value option given to its values (several only for a
    repeatable one); ``body`` is the body text when ``--body`` or ``--body-file``
    was given.

    Example: ``Call(<issue view>, {"n": "3"}, {}, frozenset({"--comments"}))``.
    """

    operation: Operation
    positionals: Mapping[str, str]
    options: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    flags: frozenset[str] = frozenset()
    body: str | None = None
    json: bool = False

    @property
    def name(self) -> str:
        """The operation's name as typed: ``"pr create"``."""
        return self.operation.name

    def value(self, option: str) -> str | None:
        """The last value given for ``option``, else ``None``."""
        values = self.options.get(option)
        return values[-1] if values else None

    def values(self, option: str) -> tuple[str, ...]:
        """Every value given for ``option`` (a repeatable one may have several)."""
        return self.options.get(option, ())

    def positional(self, name: str) -> str:
        """The positional argument ``name`` (always present: :func:`parse_call` checks it)."""
        return self.positionals[name]


def parse_call(words: Sequence[str], *, json: bool = False) -> Call:
    """The operation ``words`` (argv after ``playbook forge`` and its global options) runs.

    ``json`` is ``--json`` given before the operation. Raises
    :class:`ForgeStop` (exit 1) for an unknown operation or a usage error.

    Example::

        >>> parse_call(["issue", "view", "3", "--comments"]).flags
        frozenset({'--comments'})
    """
    found = operation_call(list(words))
    if found is None or found.directory is not None:
        shown = " ".join(words[:2]) or "(none)"
        raise ForgeStop(1, f"unknown forge operation {shown!r}; operations: {_names()}")
    operation = found.operation
    positionals: list[str] = []
    options: dict[str, list[str]] = {}
    flags: set[str] = set()
    args = list(found.args)
    while args:
        word = args.pop(0)
        name, equals, inline = word.partition("=")
        if word == _JSON:
            json = True
        elif word in operation.flags:
            flags.add(word)
        elif name in operation.values:
            if equals:
                value = inline
            elif args:
                value = args.pop(0)
            else:
                raise _usage(operation, f"{name} needs a value")
            if name in options and name not in operation.repeatable:
                raise _usage(operation, f"{name} is given twice")
            options.setdefault(name, []).append(value)
        elif word.startswith("-") and word != _STDIN:
            raise _usage(operation, f"unknown option {name}")
        else:
            positionals.append(word)
    if len(positionals) != len(operation.positionals):
        raise _usage(operation, f"expected {len(operation.positionals)} argument(s)")
    positionals = [
        _number(name, value) for name, value in zip(operation.positionals, positionals, strict=True)
    ]
    _check_choices(operation, options)
    body = _body(operation, options)  # takes the body options out of ``options``
    return Call(
        operation=operation,
        positionals=dict(zip(operation.positionals, positionals, strict=True)),
        options={name: tuple(values) for name, values in options.items()},
        flags=frozenset(flags),
        body=body,
        json=json,
    )


def operation_help(words: Sequence[str]) -> str | None:
    """The usage line of the operation ``words`` name when they ask for it (``-h``/``--help``).

    Example::

        >>> operation_help(["pr", "view", "--help"])
        'playbook forge pr view <n> [--comments]'
    """
    found = operation_call(list(words))
    if found is None or not {"-h", "--help"} & set(found.args):
        return None
    return f"playbook forge {usage(found.operation)}"


def operations_help() -> str:
    """Every operation's usage, one per line (``playbook forge`` with no operation prints it)."""
    return "\n".join(f"playbook forge {usage(operation)}" for operation in OPERATIONS)


def usage(operation: Operation) -> str:
    """One operation's usage: ``issue view <n> [--comments]``."""
    parts = [operation.name, *(f"<{name}>" for name in operation.positionals)]
    for option in sorted(operation.values):
        parts.append(f"[{option} <value>]" + ("…" if option in operation.repeatable else ""))
    parts.extend(f"[{flag}]" for flag in sorted(operation.flags))
    return " ".join(parts)


def _number(name: str, value: str) -> str:
    """An issue or pull request number given as ``#n`` or ``!n`` is ``n`` (``ref`` keeps its sigil)."""
    if name in _VERBATIM or _NUMBERED.fullmatch(value) is None:
        return value
    return value[1:]


def _names() -> str:
    return ", ".join(operation.name for operation in OPERATIONS)


def _usage(operation: Operation, problem: str) -> ForgeStop:
    return ForgeStop(1, f"{problem}; usage: playbook forge {usage(operation)}")


def _check_choices(operation: Operation, options: Mapping[str, list[str]]) -> None:
    for option, allowed in operation.choices:
        for value in options.get(option, ()):
            if value not in allowed:
                raise _usage(operation, f"{option} must be one of {', '.join(allowed)}")


def _body(operation: Operation, options: dict[str, list[str]]) -> str | None:
    """The body text, read once: ``--body TEXT``, ``--body-file PATH|-`` or ``--template PATH``."""
    given = {name: options.pop(name) for name in (_BODY, BODY_FILE, TEMPLATE) if name in options}
    if len(given) > 1:
        raise _usage(operation, f"give one of {', '.join(sorted(given))}")
    if not given:
        return None
    ((name, values),) = given.items()
    value = values[-1]
    if name == _BODY:
        return value
    if value == _STDIN and name == BODY_FILE:
        return sys.stdin.read()
    try:
        return Path(value).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ForgeStop(1, f"cannot read {name} {value}: {error}") from None
