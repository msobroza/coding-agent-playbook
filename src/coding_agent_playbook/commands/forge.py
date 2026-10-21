"""`playbook forge` — run one forge operation on GitHub or GitLab (specs/prF-forge-adapter.md §5, §6).

``playbook forge [-C <path>] <noun> <verb> [arguments] [--json]`` reads the
repo's git config on every call, maps the push remote's host to its forge and
runs that forge's CLI (``gh`` or ``glab``) with its own login and translated
arguments. Only this command contacts a forge (ADR 0003); the engine never
reads or stores a token.

Read operations print one JSON shape on both forges; write operations print the
URL of what they created or changed (``{"url": …}`` with ``--json``). Exit
codes (§6.2): ``0`` success, ``1`` the call or the forge CLI failed (its stderr
passes through), ``2`` a human must fix something (one-line hint), ``3`` the
forge or its plan lacks the operation (the skill applies its text fallback).

The command only wires the steps; each lives in a private module: the arguments
(``_forge_args``), the push remote and its forge (``_forge_repo``), the forge
CLI process (``_forge_cli``), the operations (``_forge_dispatch`` and the modules it
dispatches to) and the stops and hints (``_forge_stop``).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Final

from coding_agent_playbook.commands._forge_args import (
    operation_help,
    operations_help,
    parse_call,
)
from coding_agent_playbook.commands._forge_dispatch import perform
from coding_agent_playbook.commands._forge_repo import locate
from coding_agent_playbook.commands._forge_stop import ForgeStop

NAME: Final = "forge"
HELP: Final = "run a forge operation on GitHub or GitLab through gh or glab"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook forge [-C <path>] [--json] <noun> <verb> [arguments]``.

    The operation's own arguments are read by ``_forge_args`` from ``words``, so
    ``--json`` may also follow them.

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook forge"))  # doctest: +SKIP
    """
    parser.description = (
        "Run one forge operation (issue, pr, label, ref, which, auth) on the forge of the "
        "current branch's push remote. Run with no operation to list them."
    )
    parser.add_argument("-C", dest="directory", metavar="PATH", help="run as if started in PATH")
    parser.add_argument("--json", action="store_true", help="print a write's URL as JSON")
    parser.add_argument("words", nargs=argparse.REMAINDER, help="the operation and its arguments")


def run(args: argparse.Namespace) -> int:
    """``playbook forge``: run the operation and return its exit code (0, 1, 2 or 3)."""
    words = list(getattr(args, "words", None) or ())
    shown = operations_help() if not words else operation_help(words)
    if shown is not None:
        print(shown)
        return 0
    env = os.environ
    try:
        call = parse_call(words, json=bool(getattr(args, "json", False)))
        remote = locate(Path(getattr(args, "directory", None) or "."), env)
        outcome = perform(call, remote, env)
    except ForgeStop as stop:
        sys.stderr.write(stop.stderr)
        return stop.code
    if outcome.stderr:
        sys.stderr.write(outcome.stderr)
    if outcome.stdout:
        sys.stdout.write(outcome.stdout)
    return outcome.code
