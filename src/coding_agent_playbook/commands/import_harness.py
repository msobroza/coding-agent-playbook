"""``playbook import-harness``: exit codes and the report of ``agent_harness.importer`` (SPEC §12.9)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.agent_harness.importer import import_harness, write_import
from coding_agent_playbook.agent_harness.models import NotAHarnessError

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.agent_harness.importer import ImportResult

NAME: Final = "import-harness"
HELP: Final = "import an Agent Harness tree into canonical artifacts"
_INTO_HELP: Final = "overlay directory to write canonical artifacts into (defaults to ./playbook)"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook import-harness [PATH] [--into DIR]`` (SPEC §12.9)."""
    parser.add_argument("path", nargs="?", help="path to the harness root (contains HARNESS.md)")
    parser.add_argument("--into", help=_INTO_HELP)


def run(args: argparse.Namespace) -> int:
    """``playbook import-harness <path> [--into <dir>]``: 0 imported, 2 usage error."""
    root = Path(args.path) if getattr(args, "path", None) else None
    into = Path(args.into) if getattr(args, "into", None) else Path.cwd() / "playbook"
    if root is None or not root.is_dir():
        problem = f"{root} is not a directory" if root else "import-harness requires a harness path"
        print(f"error: {problem}", file=sys.stderr)
        return 2
    try:
        result = import_harness(root)
    except NotAHarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_import(result, into)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(_summary(result, into))
    return 0


def _summary(result: ImportResult, into: Path) -> str:
    """``imported N artifact(s) into <dir> (... rules, ... prompts, ... skills, ... hooks)``."""
    counts = {
        "rules": len(result.rules),
        "prompts": len(result.prompts),
        "skills": len(result.skills),
        "hooks": len(result.hooks),
    }
    detail = ", ".join(f"{count} {kind}" for kind, count in counts.items())
    return f"imported {sum(counts.values())} artifact(s) into {into} ({detail})"
