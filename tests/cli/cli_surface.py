"""The structural surface of the ``playbook`` parser, pinned by the CLI surface golden.

The surface lists every subcommand in ``playbook --help`` order with its help
line, the ``run`` it dispatches to and, for each argparse action, the fields that
decide what parses and what ``--help`` says: the action class, ``option_strings``,
``dest``, ``nargs``, ``const``, ``default``, the ``type`` name, ``choices``,
``required``, ``help`` and ``metavar``, plus the mutually exclusive groups
(specs/prT-package-layout.md B.12.4). It is read from the parser objects, never
from ``--help`` text, whose layout differs between Python 3.12 and 3.13, so one
golden serves every supported Python.

Re-record ``tests/cli/golden/cli_surface.json`` only when a flag changes on
purpose, and review the diff::

    python -m tests.cli.cli_surface
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

__all__ = ["GOLDEN_PATH", "cli_surface", "parser_surface", "record_golden"]

GOLDEN_PATH: Final = Path(__file__).parent / "golden" / "cli_surface.json"

#: JSON's own scalars, kept as they are; anything else is pinned by its repr.
_JSON_SCALARS: Final = (str, int, float, bool, type(None))


def cli_surface(parser: argparse.ArgumentParser) -> dict[str, object]:
    """The whole ``playbook`` surface: the top-level options, then each subcommand.

    Example::

        >>> cli_surface(build_parser())["subcommands"][0]["name"]  # doctest: +SKIP
        'init'
    """
    return {
        "prog": parser.prog,
        "description": parser.description,
        "actions": [_action_surface(action) for action in parser._actions],
        "subcommands": _subcommand_surfaces(parser),
    }


def parser_surface(parser: argparse.ArgumentParser) -> dict[str, object]:
    """One (sub)parser's description, actions in declaration order and exclusive groups.

    Example::

        >>> parser_surface(argparse.ArgumentParser())["exclusive_groups"]
        []
    """
    return {
        "description": parser.description,
        "actions": [_action_surface(action) for action in parser._actions],
        "exclusive_groups": [
            {"required": group.required, "dests": [a.dest for a in group._group_actions]}
            for group in parser._mutually_exclusive_groups
        ],
    }


def record_golden(path: Path = GOLDEN_PATH) -> None:
    """Write the current parser's surface to ``path`` (a deliberate flag change only).

    Example::

        >>> record_golden(Path("/tmp/cli_surface.json"))  # doctest: +SKIP
    """
    from coding_agent_playbook.cli.parser import build_parser

    text = json.dumps(cli_surface(build_parser()), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _subcommand_surfaces(parser: argparse.ArgumentParser) -> list[dict[str, object]]:
    """Each subparser, in registration order, with its help line and its ``func`` default."""
    group = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps = {choice.dest: choice.help for choice in group._choices_actions}
    return [
        {
            "name": name,
            "help": helps.get(name),
            "func": _qualified_name(sub.get_default("func")),
            **parser_surface(sub),
        }
        for name, sub in group.choices.items()
    ]


def _action_surface(action: argparse.Action) -> dict[str, object]:
    """The fields of one action that decide what parses and what ``--help`` prints."""
    choices = action.choices
    if isinstance(action, argparse._SubParsersAction):
        choices = list(action.choices)  # the subparsers themselves are pinned one by one
    return {
        "action": type(action).__name__,
        "option_strings": list(action.option_strings),
        "dest": action.dest,
        "nargs": _jsonable(action.nargs),
        "const": _jsonable(action.const),
        "default": _jsonable(action.default),
        "type": _type_name(action.type),
        "choices": _jsonable(choices),
        "required": action.required,
        "help": action.help,
        "metavar": _jsonable(action.metavar),
    }


def _jsonable(value: object) -> object:
    """``value`` as JSON: scalars as they are, sequences as lists, anything else as its repr."""
    if isinstance(value, _JSON_SCALARS):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return repr(value)


def _type_name(converter: object) -> str | None:
    """An action's ``type`` by name (``int``), so the golden does not hold an object repr."""
    if converter is None:
        return None
    return getattr(converter, "__name__", repr(converter))


def _qualified_name(func: object) -> str | None:
    """``module.qualname`` of a subcommand's ``func`` default, or None when it has none."""
    if func is None:
        return None
    return f"{getattr(func, '__module__', '?')}.{getattr(func, '__qualname__', '?')}"


if __name__ == "__main__":
    record_golden()
