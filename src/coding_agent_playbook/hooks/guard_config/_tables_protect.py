"""The ``sentinel`` and ``protected`` tables of ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5, §E.1).

guard-generated-outputs (and, in later K5 steps, control-plane-guard and the
``drift`` Stop stage) decide what is generated from data rendered here at sync,
so the hot path never renders a template or spawns ``playbook``:

- ``entries``: the sync's written set as lock rows ``{path, kind, artifact_id,
  source, scope}``, exactly what the lockfile records (P4 provenance), plus
  ``sha256`` on the scoped rows (the managed ``settings.json`` elements), so
  control-plane-guard can tell a managed element from a user one;
- ``output_dirs``: each enabled adapter's sentinel-scanned ``_output_directories()``
  (repo-relative, trailing ``/``) plus its composite singletons, the files a
  sentinel can mark as engine output;
- ``hook_artifacts``: the guardrail files themselves, which only the user may change;
- ``resource_roots``: package-relative ids (``pkg:<package>/resources``) of the
  engine and every ``overlays_enabled`` layer (``resource_roots``).

Everything is machine-independent (§D.8.3): ``sync --check`` byte-compares it.
The rows and the output dirs need the adapters, so sync assembles them
(``sync._protect``) and hands them over as ``inputs.ProtectInputs``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hooks.guard_config.resource_roots import resource_root_ids

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hooks.guard_config.inputs import ProtectInputs

__all__ = ["protected_table"]


def protected_table(inputs: ProtectInputs, hook_artifacts: Sequence[str]) -> dict[str, Any]:
    """The ``protected`` table: sorted rows, output dirs, hook artifacts, resource ids.

    Example::

        >>> protected_table(ProtectInputs(), ())["entries"]
        []
    """
    rows = sorted(inputs.entries, key=lambda row: (row.path, row.scope))
    return {
        "entries": [row.to_json() for row in rows],
        "output_dirs": sorted(set(inputs.output_dirs)),
        "hook_artifacts": list(hook_artifacts),
        "resource_roots": resource_root_ids(inputs.packages),
    }
