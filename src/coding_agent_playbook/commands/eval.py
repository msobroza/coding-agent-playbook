"""`cap eval` — PR-11 deferral stub (SPEC §12.8).

PR 11 ships the read-only eval enumeration (``--list``/``--show``) and the
schema validator. The v2 runner remains absent. This stub keeps the CLI
shape stable so consumers can wire ``cap eval`` into CI today as a no-op
placeholder that won't break the pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


_DEFERRAL_MESSAGE = (
    "cap eval is not implemented yet; PR 11 ships the read-only eval enumeration "
    "(--list / --show) and the schema validator. The v2 runner remains absent — "
    "see SPEC §6.5.6 'what runs in v1' for the full deferral matrix."
)


def run(args: argparse.Namespace) -> int:
    """Print the deferral message regardless of which variant the user
    asked for (``--list``, ``--show <id>``, or bare ``<id>``).
    """
    if getattr(args, "list", False):
        prefix = "cap eval --list"
    elif getattr(args, "show", None):
        prefix = f"cap eval --show {args.show}"
    elif getattr(args, "id", None):
        prefix = f"cap eval {args.id}"
    else:
        prefix = "cap eval"
    print(f"{prefix}: {_DEFERRAL_MESSAGE}")
    return 0
