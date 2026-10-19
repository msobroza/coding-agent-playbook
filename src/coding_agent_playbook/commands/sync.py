"""`playbook sync` — regenerate all artifacts (SPEC §12.2 / §12.3).

The command only reads its flags: the sync pipeline it runs (write mode, ``--check``
and ``--check-staged``) is :func:`coding_agent_playbook.sync.pipeline.execute`, which
``playbook init`` calls too.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.sync import pipeline

if TYPE_CHECKING:
    import argparse

NAME: Final = "sync"
HELP: Final = "regenerate all artifacts (SPEC §12.2)"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook sync [--repo-root R] [--check | --check-staged]`` (SPEC §12.3).

    Example: ``configure(argparse.ArgumentParser(prog="playbook sync"))``.
    """
    parser.add_argument("--repo-root", help="repo to sync (defaults to cwd)")
    sync_mode = parser.add_mutually_exclusive_group()
    sync_mode.add_argument(
        "--check",
        action="store_true",
        help="verify against the lockfile without writing (SPEC §12.3)",
    )
    sync_mode.add_argument(
        "--check-staged",  # the commit = false pre-commit guard (no-op if commit = true)
        dest="check_staged",
        action="store_true",
        help="fail if any staged path is generated output; never writes (SPEC §12.3)",
    )


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    raw = getattr(args, "repo_root", None)
    return Path.cwd() if raw is None else Path(raw)


def run(args: argparse.Namespace) -> int:
    """Dispatch the parsed ``playbook sync`` flags to :func:`pipeline.execute`."""
    return pipeline.execute(
        repo_root=_resolve_repo_root(args),
        check=bool(getattr(args, "check", False)),
        check_staged=bool(getattr(args, "check_staged", False)),
    )
