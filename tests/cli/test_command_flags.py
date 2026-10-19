"""``init``, ``sync``, ``validate`` and ``render`` keep their flags after declaring them (CP-1, CP-3).

The flag table of each subcommand (``option_strings``, ``dest``, ``default``,
``choices``, ``nargs``, ``help`` and the mutually exclusive groups) is compared
with ``tests/cli/golden/cli_surface.json``, which B9 recorded from
``build_parser()`` before any flag left ``cli/parser.py``
(specs/prT-package-layout.md AC.5.6, B.12.4). Each migrated module's
``configure`` must also parse today's flag sets on a parser of its own.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import init as init_cmd
from coding_agent_playbook.commands import render as render_cmd
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.commands import validate as validate_cmd
from tests.cli.cli_surface import GOLDEN_PATH, cli_surface

if TYPE_CHECKING:
    from types import ModuleType

#: The fields of one flag row the table pins (AC.5.6).
_ROW_FIELDS = ("option_strings", "dest", "default", "choices", "nargs", "help")

#: Each migrated command, with argv it must accept and the flags those set.
_ACCEPTED_ARGV: Final = [
    (
        init_cmd,
        ["--non-interactive", "--name", "x", "--kind", "python-library"],
        {"non_interactive": True, "name": "x", "kind": "python-library", "overlays": None},
    ),
    (
        init_cmd,
        ["--no-hooks", "--adapters", "continue"],
        {"no_hooks": True, "adapters": "continue"},
    ),
    (sync_cmd, ["--check"], {"check": True, "check_staged": False, "repo_root": None}),
    (sync_cmd, ["--check-staged"], {"check": False, "check_staged": True}),
    (sync_cmd, ["--repo-root", "/r"], {"check": False, "repo_root": "/r"}),
    (validate_cmd, ["--repo-root", "/r"], {"repo_root": "/r"}),
    (render_cmd, ["rules.x", "--show-rules"], {"id": "rules.x", "show_rules": True}),
    (
        render_cmd,
        ["p", "--format", "md", "--show-source"],
        {"id": "p", "format": "md", "show_source": True, "show_rules": False},
    ),
]


def _flag_table(surface: dict[str, object]) -> dict[str, object]:
    """The pinned rows of one (sub)parser surface, in declaration order."""
    actions = surface["actions"]
    assert isinstance(actions, list)
    return {
        "rows": [{field: action[field] for field in _ROW_FIELDS} for action in actions],
        "exclusive_groups": surface["exclusive_groups"],
    }


def _subcommand(surface: dict[str, object], name: str) -> dict[str, object]:
    """The entry of subcommand ``name`` in a whole-CLI surface (``cli_surface``'s shape)."""
    subcommands = surface["subcommands"]
    assert isinstance(subcommands, list)
    entry: dict[str, object] = next(item for item in subcommands if item["name"] == name)
    return entry


@pytest.mark.parametrize("name", ["init", "sync", "validate", "render"])
def test_flag_table_is_unchanged(name: str) -> None:
    """``build_parser`` gives each subcommand the flag rows recorded before the move."""
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    built = _flag_table(_subcommand(cli_surface(build_parser()), name))

    assert built == _flag_table(_subcommand(golden, name))


@pytest.mark.parametrize(
    ("command", "argv", "expected"),
    [pytest.param(*case, id=f"{case[0].NAME} {' '.join(case[1])}") for case in _ACCEPTED_ARGV],
)
def test_each_command_parses_its_flags_alone(
    command: ModuleType, argv: list[str], expected: dict[str, object]
) -> None:
    """A parser built from the module's ``configure`` alone accepts today's flag sets."""
    parser = argparse.ArgumentParser(prog=f"playbook {command.NAME}")
    command.configure(parser)

    parsed = vars(parser.parse_args(argv))

    assert {key: parsed[key] for key in expected} == expected


def test_sync_check_and_check_staged_exclude_each_other(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--check --check-staged`` is an argparse usage error (exit 2), as before the move."""
    parser = argparse.ArgumentParser(prog="playbook sync")
    sync_cmd.configure(parser)

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--check", "--check-staged"])

    assert exc.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
