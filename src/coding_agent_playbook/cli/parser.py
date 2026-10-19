"""The ``playbook`` argument parser: one subparser per subcommand, built by name.

Each subcommand lives in its own module under ``coding_agent_playbook.commands``
and exposes a ``run(args) -> int`` that returns the process exit code. A module
on the Command protocol (:mod:`._command`) also declares its ``NAME``, ``HELP``
and flags (``configure``), and :func:`build_parser` walks ``_SUBCOMMANDS`` by
name: a name in ``_COMMANDS`` gets the module's flags, a name in ``_LEGACY``
still has them declared here, until its command migrates (CP-3, B10).

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
    sync_cmd,
    check_cmd,
    validate_cmd,
    render_cmd,
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


def _add_eval_parser(subcommands: _SubParsers) -> None:
    """``playbook eval``'s flags (PR 11 enumeration; PR R1d adds --run); B10 moves them."""
    eval_p = subcommands.add_parser(
        "eval", help="eval enumeration + `--run` a task (SPEC §12.8, §15)"
    )
    # Every other subcommand exposes ``--repo-root <path>`` for testability
    # and so users can run against a non-cwd checkout; eval gets the same
    # surface for parity. The command runner in ``commands/eval.py`` already
    # falls back to ``Path.cwd()`` when this is absent.
    eval_p.add_argument(
        "--repo-root", help="repo to enumerate eval tasks against (defaults to cwd)"
    )
    eval_group = eval_p.add_mutually_exclusive_group()
    eval_group.add_argument("--list", action="store_true")
    eval_group.add_argument("--show", help="show one task by id")
    eval_p.add_argument("id", nargs="?", help="task id (enumerate, or run with --run)")
    # PR R1d — execute one task end-to-end and grade it through the unified
    # EvaluationReport. Whether execution evaluators run is the task's own
    # [metrics] decision, so there is intentionally no --run-tests flag here.
    eval_p.add_argument(
        "--run",
        action="store_true",
        help="execute the task <id> through a runner and grade it (SPEC §15)",
    )
    eval_p.add_argument(
        "--runner",
        help="runner name from the coding_agent_playbook.runners group "
        "(default: claude_code; use 'fake' for a hermetic no-op run)",
    )
    # PR R2 — judged [rubric] scoring. --judge selects a Tier-2 judge from the
    # coding_agent_playbook.judges group (e.g. 'llm', opt-in/CLI-gated); omitted
    # means deterministic-only. --samples is the per-criterion average count.
    eval_p.add_argument(
        "--judge",
        help="judge name from the coding_agent_playbook.judges group to score "
        "[rubric] criteria (e.g. 'llm'); omit for a deterministic-only run",
    )
    eval_p.add_argument(
        "--samples",
        type=int,
        help="per-criterion judge samples to average (default: 1)",
    )
    # By default --run is fail-fast: a lost deterministic gate skips the costlier
    # judge tier (saving an LLM call). --full-scoring grades every check.
    eval_p.add_argument(
        "--full-scoring",
        action="store_true",
        help="grade every check even after the gate is lost (disables fail-fast; "
        "scores the judge tier regardless of a failing deterministic check)",
    )
    eval_p.add_argument(
        "--format",
        choices=("text", "json"),
        help="--run output format (default: text)",
    )
    eval_p.set_defaults(func=eval_cmd.run)


#: The subcommands whose flags are still declared here, by name; each moves into
#: its command module and onto ``_COMMANDS`` (B10: eval; CP-3: init), and the
#: mapping goes with the last of them.
_LEGACY: Final[Mapping[str, Callable[[_SubParsers], None]]] = {
    "init": _add_init_parser,
    "eval": _add_eval_parser,
}
