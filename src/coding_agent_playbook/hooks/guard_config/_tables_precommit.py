"""The ``precommit`` table of ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5, §E.1).

The playbook hook ids of the repo's ``.pre-commit-config.yaml``, scanned with the
runtime's own regex so control-plane-guard and sync never disagree on which ids
the user may not remove. Read from the real repo in every mode (``--check``
renders into an empty scratch directory): one of the repo readers
``compile_guard_config`` calls itself (``_repo_inputs``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.schema import (
    PRECOMMIT_CONFIG,
    playbook_precommit_ids,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["precommit_hook_ids"]

#: Pre-commit configs are small; a larger one is not scanned.
_PRECOMMIT_MAX_BYTES: Final = 1024 * 1024


def precommit_hook_ids(repo_root: Path) -> list[str]:
    """The playbook hook ids of ``<repo_root>/.pre-commit-config.yaml`` (``[]`` without one).

    The runtime's own regex, never ``yaml``: control-plane-guard denies the
    removal of exactly these ids.

    Example::

        >>> precommit_hook_ids(Path("/no/such/repo"))
        []
    """
    try:
        with (repo_root / PRECOMMIT_CONFIG).open("rb") as handle:
            data = handle.read(_PRECOMMIT_MAX_BYTES + 1)
    except OSError:
        return []
    if len(data) > _PRECOMMIT_MAX_BYTES:
        return []
    return playbook_precommit_ids(data.decode("utf-8", errors="replace"))
