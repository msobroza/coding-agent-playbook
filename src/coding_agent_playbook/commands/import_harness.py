"""``playbook import-harness <path> [--into <dir>]`` (PR H Track H3).

The command half: argument checks, exit codes and the report. The importer itself
(:func:`~coding_agent_playbook.agent_harness.importer.import_harness` and
:func:`~coding_agent_playbook.agent_harness.importer.write_import`) lives in the
agent_harness package beside the adapter that writes the tree (AH-1, #134).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.agent_harness.importer import import_harness, write_import
from coding_agent_playbook.agent_harness.models import NotAHarnessError

if TYPE_CHECKING:
    import argparse

NAME: Final = "import-harness"
HELP: Final = "import an Agent Harness tree into canonical artifacts"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook import-harness [PATH] [--into DIR]`` (SPEC §12.9).

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook import-harness"))  # doctest: +SKIP
    """
    parser.add_argument("path", nargs="?", help="path to the harness root (contains HARNESS.md)")
    parser.add_argument(
        "--into",
        help="overlay directory to write canonical artifacts into (defaults to ./playbook)",
    )


def run(args: argparse.Namespace) -> int:
    """``playbook import-harness <path> [--into <dir>]`` (SPEC §12)."""
    raw_path = getattr(args, "path", None)
    if not raw_path:
        print("error: import-harness requires a harness path", file=sys.stderr)
        return 2
    harness_root = Path(raw_path)
    into = Path(args.into) if getattr(args, "into", None) else Path.cwd() / "playbook"

    if not harness_root.is_dir():
        print(f"error: {harness_root} is not a directory", file=sys.stderr)
        return 2
    try:
        result = import_harness(harness_root)
    except NotAHarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    write_import(result, into)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    count = len(result.rules) + len(result.prompts) + len(result.skills) + len(result.hooks)
    print(
        f"imported {count} artifact(s) into {into} "
        f"({len(result.rules)} rules, {len(result.prompts)} prompts, "
        f"{len(result.skills)} skills, {len(result.hooks)} hooks)"
    )
    return 0
