"""`playbook sync` — regenerate all artifacts (SPEC §12.2 / §12.3).

The command only reads its flags: the sync pipeline it runs (write mode,
``--check`` and ``--check-staged``) is
:func:`coding_agent_playbook.sync.pipeline.execute`, which ``playbook init``
calls too.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.sync import pipeline

if TYPE_CHECKING:
    import argparse


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    raw = getattr(args, "repo_root", None)
    if raw is None:
        return Path.cwd()
    return Path(raw)


def run(args: argparse.Namespace) -> int:
    """Dispatch the parsed ``playbook sync`` flags to :func:`pipeline.execute`."""
    return pipeline.execute(
        repo_root=_resolve_repo_root(args),
        check=bool(getattr(args, "check", False)),
        check_staged=bool(getattr(args, "check_staged", False)),
    )
