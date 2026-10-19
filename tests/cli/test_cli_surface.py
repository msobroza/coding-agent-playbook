"""The ``playbook`` flags stay as they were while commands take over their declaration.

``tests/cli/golden/cli_surface.json`` was recorded from ``build_parser()`` before
any flag left ``cli/parser.py`` (specs/prT-package-layout.md B.12.4): every
subcommand's help line, dispatch target, flags (with their defaults, help text and
choices) and mutually exclusive groups. A command that declares its own flags must
reproduce its golden entry exactly, through ``build_parser`` and on its own.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli.parser import _COMMANDS, build_parser
from tests.cli.cli_surface import GOLDEN_PATH, cli_surface, parser_surface, record_golden

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.cli._command import Command


def _golden() -> dict[str, object]:
    loaded: dict[str, object] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return loaded


def _golden_subcommand(name: str) -> dict[str, object]:
    subcommands = _golden()["subcommands"]
    assert isinstance(subcommands, list)
    return next(entry for entry in subcommands if entry["name"] == name)


def test_every_subcommand_keeps_its_flags() -> None:
    assert cli_surface(build_parser()) == _golden()


@pytest.mark.parametrize("command", _COMMANDS, ids=lambda command: command.NAME)
def test_each_command_declares_its_golden_flags_alone(command: Command) -> None:
    """``configure`` on a bare parser yields the flags ``build_parser`` gave the subcommand."""
    parser = argparse.ArgumentParser(prog=f"playbook {command.NAME}")

    command.configure(parser)

    golden = _golden_subcommand(command.NAME)
    assert parser_surface(parser) == {key: golden[key] for key in parser_surface(parser)}
    assert (command.HELP, f"{command.run.__module__}.run") == (golden["help"], golden["func"])


def test_surface_sees_a_changed_flag() -> None:
    """The golden is not blind: a help line, a default or a group change alters the surface."""

    def parser_with(help_text: str, default: str, grouped: bool) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        target = parser.add_mutually_exclusive_group() if grouped else parser
        target.add_argument("--format", default=default, help=help_text)
        return parser

    base = parser_surface(parser_with("output format", "text", grouped=False))

    assert parser_surface(parser_with("output format", "text", grouped=False)) == base
    assert parser_surface(parser_with("the format", "text", grouped=False)) != base
    assert parser_surface(parser_with("output format", "json", grouped=False)) != base
    assert parser_surface(parser_with("output format", "text", grouped=True)) != base


def test_record_golden_writes_the_current_surface(tmp_path: Path) -> None:
    """``python -m tests.cli.cli_surface`` writes what the golden test compares against."""
    target = tmp_path / "cli_surface.json"

    record_golden(target)

    assert json.loads(target.read_text(encoding="utf-8")) == cli_surface(build_parser())
    assert target.read_text(encoding="utf-8") == GOLDEN_PATH.read_text(encoding="utf-8")
