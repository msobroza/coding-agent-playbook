"""The ``playbook`` argument parser: one subparser per Command module, in ``--help`` order.

Each subcommand lives in its own module under ``coding_agent_playbook.commands``
and is a Command (:mod:`._command`): it declares its ``NAME``, ``HELP`` and
flags (``configure``) next to the ``run(args) -> int`` that returns the process
exit code. :func:`build_parser` walks ``_COMMANDS``, so this module declares no
subcommand flag (CP-3 moved the last ones, ``init``'s, into their command).

The dispatch pattern is the standard ``subparser.set_defaults(func=...)``
idiom: ``coding_agent_playbook.cli.main()`` parses argv with :func:`build_parser`,
then calls ``args.func(args)`` if a subcommand was selected, else falls back to
printing help. ``build_parser`` reads each ``run`` when it is called, so a test
that patches a command module's ``run`` before calling ``main`` still reaches it.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

from coding_agent_playbook import __version__
from coding_agent_playbook.commands import check as check_cmd
from coding_agent_playbook.commands import eval as eval_cmd
from coding_agent_playbook.commands import forge as forge_cmd
from coding_agent_playbook.commands import import_harness as import_harness_cmd
from coding_agent_playbook.commands import init as init_cmd
from coding_agent_playbook.commands import metrics as metrics_cmd
from coding_agent_playbook.commands import render as render_cmd
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.commands import validate as validate_cmd
from coding_agent_playbook.commands import validate_harness as validate_harness_cmd
from coding_agent_playbook.commands.twins import check_commit_trailers as check_commit_trailers_cmd
from coding_agent_playbook.commands.twins import check_deps as check_deps_cmd
from coding_agent_playbook.commands.twins import check_notebooks as check_notebooks_cmd
from coding_agent_playbook.commands.twins import ci as ci_cmd
from coding_agent_playbook.commands.twins import gate_scan as gate_scan_cmd
from coding_agent_playbook.commands.twins import scan_secrets as scan_secrets_cmd
from coding_agent_playbook.commands.twins import scan_sinks as scan_sinks_cmd

if TYPE_CHECKING:
    from coding_agent_playbook.cli._command import Command

#: Every subcommand module, in the order ``playbook --help`` lists them.
_COMMANDS: Final[tuple[Command, ...]] = (
    init_cmd,
    sync_cmd,
    check_cmd,
    validate_cmd,
    render_cmd,
    eval_cmd,
    metrics_cmd,
    import_harness_cmd,
    validate_harness_cmd,
    forge_cmd,
    gate_scan_cmd,
    ci_cmd,
    scan_sinks_cmd,
    check_notebooks_cmd,
    scan_secrets_cmd,
    check_commit_trailers_cmd,
    check_deps_cmd,
)

#: The subcommand names in ``--help`` order; the public surface tests pin them.
_SUBCOMMANDS: Final[tuple[str, ...]] = tuple(command.NAME for command in _COMMANDS)


def build_parser() -> argparse.ArgumentParser:
    """The ``playbook`` parser: one subparser per module of ``_COMMANDS``, in that order.

    Example::

        >>> build_parser().parse_args(["check", "--refresh"]).refresh
        True
    """
    parser = argparse.ArgumentParser(
        prog="playbook",
        description="coding-agent-playbook — multi-harness playbook engine.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"coding-agent-playbook {__version__}",
    )
    subcommands = parser.add_subparsers(dest="command")
    for command in _COMMANDS:
        sub = subcommands.add_parser(command.NAME, help=command.HELP)
        command.configure(sub)
        sub.set_defaults(func=command.run)  # read now, so a patched run is the one dispatched
    return parser
