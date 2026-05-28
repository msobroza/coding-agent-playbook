"""``cap`` / ``coding-agent-playbook`` entry point.

PR 1 ships only ``--version``. Subcommands (``init``, ``sync``, ``check``,
``validate``, ``render``, ``eval``) print a deferred-implementation message and
exit 0. They are wired up by later PRs (10, 11).
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__

if TYPE_CHECKING:
    from collections.abc import Sequence

_DEFERRED_SUBCOMMANDS = ("init", "sync", "check", "validate", "render", "eval")
_DEFERRED_MESSAGE = (
    "{name!r} is not implemented yet. PR 1 ships the scaffolding only. "
    "See SPEC.md Section 12 for the planned CLI surface."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cap",
        description="coding-agent-playbook — multi-harness playbook engine.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"coding-agent-playbook {__version__}",
    )
    subcommands = parser.add_subparsers(dest="command")
    for name in _DEFERRED_SUBCOMMANDS:
        subcommands.add_parser(name, help=f"(deferred — see SPEC §12) {name}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(_DEFERRED_MESSAGE.format(name=args.command), file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
