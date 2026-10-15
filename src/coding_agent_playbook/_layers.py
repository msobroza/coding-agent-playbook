"""The artifact layer labels every ``source_package`` is compared against (SPEC §11).

A module with no imports, so the stdlib-only ``hook_policy`` can tell a
repo-local definition from an overlay's without importing ``sources.filesystem``
(and, through it, yaml). ``sources.filesystem`` re-exports both names.
"""

from __future__ import annotations

from typing import Final

#: The engine's own package: the first artifact layer.
ENGINE_PACKAGE: Final = "coding_agent_playbook"

#: ``source_package`` of every artifact under ``<repo>/playbook/``: the last layer.
REPO_LOCAL_SOURCE: Final = "<repo-local>"
