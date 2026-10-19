"""The ``playbook`` argument parser: one subparser per subcommand, built by name.

Each subcommand lives in its own module under ``coding_agent_playbook.commands``
and exposes a ``run(args) -> int`` that returns the process exit code. A module
on the Command protocol (:mod:`._command`) also declares its ``NAME``, ``HELP``
and flags (``configure``), and :func:`build_parser` walks ``_SUBCOMMANDS`` by
name: a name in ``_COMMANDS`` gets the module's flags, a name in ``_LEGACY``
still has them declared here, until its command migrates (CP-1, CP-3).

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
from coding_agent_playbook.commands import import_harness as import_harness_cmd
from coding_agent_playbook.commands import init as init_cmd
from coding_agent_playbook.commands import metrics as metrics_cmd
from coding_agent_playbook.commands import render as render_cmd
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.commands import validate as validate_cmd
from coding_agent_playbook.commands import validate_harness as validate_harness_cmd
from coding_agent_playbook.commands._init_adapters import ADAPTERS_FLAG_HELP
from coding_agent_playbook.commands.twins import check_commit_trailers as check_commit_trailers_cmd
from coding_agent_playbook.commands.twins import check_deps as check_deps_cmd
from coding_agent_playbook.commands.twins import check_notebooks as check_notebooks_cmd
from coding_agent_playbook.commands.twins import ci as ci_cmd
from coding_agent_playbook.commands.twins import gate_scan as gate_scan_cmd
from coding_agent_playbook.commands.twins import scan_secrets as scan_secrets_cmd
from coding_agent_playbook.commands.twins import scan_sinks as scan_sinks_cmd

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.cli._command import Command

type _SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]

#: The order ``playbook --help`` lists, and the public surface tests pin. Every
#: name is a Command of ``_COMMANDS`` or a ``_LEGACY`` key, never both.
_SUBCOMMANDS: tuple[str, ...] = (
    "init",
    "sync",
    "check",
    "validate",
    "render",
    "eval",
    "metrics",
    "import-harness",
    "validate-harness",
    "gate-scan",
    "ci",
    "scan-sinks",
    "check-notebooks",
    "scan-secrets",
    "check-commit-trailers",
    "check-deps",
)

#: The subcommand modules that declare their own flags, in ``_SUBCOMMANDS`` order.
_COMMANDS: Final[tuple[Command, ...]] = (
    check_cmd,
    eval_cmd,
    metrics_cmd,
    import_harness_cmd,
    validate_harness_cmd,
    gate_scan_cmd,
    ci_cmd,
    scan_sinks_cmd,
    check_notebooks_cmd,
    scan_secrets_cmd,
    check_commit_trailers_cmd,
    check_deps_cmd,
)


def build_parser() -> argparse.ArgumentParser:
    """The ``playbook`` parser: one subparser per name of ``_SUBCOMMANDS``, looked up by name.

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
    commands = {command.NAME: command for command in _COMMANDS}
    for name in _SUBCOMMANDS:
        _add_subcommand(subcommands, name, commands)
    return parser


def _add_subcommand(subcommands: _SubParsers, name: str, commands: Mapping[str, Command]) -> None:
    """Register ``name``: from its Command module when it has one, else its ``_LEGACY`` block."""
    command = commands.get(name)
    if command is not None:
        sub = subcommands.add_parser(command.NAME, help=command.HELP)
        command.configure(sub)
        sub.set_defaults(func=command.run)  # read now, so a patched run is the one dispatched
        return
    add_legacy = _LEGACY.get(name)
    if add_legacy is None:
        raise LookupError(f"subcommand {name!r} is neither in _COMMANDS nor in _LEGACY")
    add_legacy(subcommands)


def _add_init_parser(subcommands: _SubParsers) -> None:
    """``playbook init``'s flags (SPEC §12.1); CP-3 moves them into ``commands/init.py``."""
    init_p = subcommands.add_parser("init", help="bootstrap a fresh repo (SPEC §12.1)")
    init_p.add_argument("--repo-root", help="repo to initialise (defaults to cwd)")
    init_p.add_argument("--non-interactive", action="store_true")
    init_p.add_argument("--name", help="project name (required in non-interactive mode)")
    init_p.add_argument("--kind", help="project kind (required in non-interactive mode)")
    init_p.add_argument("--description", default="")
    init_p.add_argument("--adapters", help=ADAPTERS_FLAG_HELP)
    init_p.add_argument("--overlays", help="comma-separated overlay package names")
    init_p.add_argument(
        "--no-hooks",
        dest="no_hooks",
        action="store_true",
        help="do not enable assistant lifecycle hooks (writes [hooks] enabled = false)",
    )
    init_p.set_defaults(func=init_cmd.run)


def _add_sync_parser(subcommands: _SubParsers) -> None:
    """``playbook sync``'s flags (SPEC §12.2, §12.3); CP-1 moves them into its module."""
    sync_p = subcommands.add_parser("sync", help="regenerate all artifacts (SPEC §12.2)")
    sync_p.add_argument("--repo-root", help="repo to sync (defaults to cwd)")
    sync_mode = sync_p.add_mutually_exclusive_group()
    sync_mode.add_argument(
        "--check",
        action="store_true",
        help="verify against the lockfile without writing (SPEC §12.3)",
    )
    # [output] commit = false pre-commit guard: generated output is local-only,
    # so a commit that stages any of it fails. A no-op under commit = true.
    sync_mode.add_argument(
        "--check-staged",
        dest="check_staged",
        action="store_true",
        help="fail if any staged path is generated output; never writes (SPEC §12.3)",
    )
    sync_p.set_defaults(func=sync_cmd.run)


def _add_validate_parser(subcommands: _SubParsers) -> None:
    """``playbook validate``'s flags (SPEC §12.6); CP-1 moves them into its module."""
    validate_p = subcommands.add_parser("validate", help="cross-reference checks (SPEC §12.6)")
    validate_p.add_argument("--repo-root", help="repo to validate (defaults to cwd)")
    validate_p.set_defaults(func=validate_cmd.run)


def _add_render_parser(subcommands: _SubParsers) -> None:
    """``playbook render``'s flags (SPEC §12.7); CP-1 moves them into its module."""
    render_p = subcommands.add_parser("render", help="render one artifact (SPEC §12.7)")
    render_p.add_argument("id", help="artifact id to render")
    render_p.add_argument("--repo-root", help="repo to render against (defaults to cwd)")
    render_p.add_argument("--format", help="format alias or full name")
    render_p.add_argument("--show-source", action="store_true")
    render_p.add_argument("--show-rules", action="store_true")
    render_p.set_defaults(func=render_cmd.run)


#: The subcommands whose flags are still declared here, by name; each moves into
#: its command module and onto ``_COMMANDS`` (CP-1: sync, validate, render;
#: CP-3: init), and the mapping goes with the last of them.
_LEGACY: Final[Mapping[str, Callable[[_SubParsers], None]]] = {
    "init": _add_init_parser,
    "sync": _add_sync_parser,
    "validate": _add_validate_parser,
    "render": _add_render_parser,
}
