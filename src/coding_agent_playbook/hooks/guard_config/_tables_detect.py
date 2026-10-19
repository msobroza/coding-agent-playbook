"""The ``facts`` and ``applicability`` tables of ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5, §E.1).

- ``facts``: the detector's dependency names (runtime and dev groups) and the
  presence flags (``has_dockerfile``, ``has_ci``, ``has_notebooks``), the
  subset of ``detect()`` a mid-session edit can change, plus the detected
  ``package_manager`` (dependency-allowlist-guard, §E.4);
- ``applicability``: the rows of ``inputs.applicability_rows``, sorted.

resync-on-detector-input-change decides from these, so its cheap path is one
``tomllib`` read and a set comparison. The rows and their value types are in
``inputs`` (what sync hands the writer); this module only renders them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hooks.guard_config.inputs import ApplicabilityRow

__all__ = ["applicability_table", "facts_table"]

_FLAGS: Final = ("has_ci", "has_dockerfile", "has_notebooks")


def facts_table(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The ``facts`` table: sorted dependency names, the presence flags, the package manager.

    Example::

        >>> facts_table({"dependencies": {"torch": ">=2"}})["dependencies"]
        ['torch']
    """
    table: dict[str, Any] = {
        "dependencies": sorted(facts.get("dependencies", {})),
        "dev_dependencies": sorted(facts.get("dev_dependencies", {})),
    }
    table.update({flag: bool(facts.get(flag, False)) for flag in _FLAGS})
    manager = facts.get("package_manager")
    if isinstance(manager, str):  # dependency-allowlist-guard's tier (a), §E.4
        table["package_manager"] = manager
    return table


def applicability_table(rows: Iterable[ApplicabilityRow]) -> list[dict[str, Any]]:
    """The rendered ``applicability`` list, sorted by ``(kind, id)``.

    Example::

        >>> applicability_table([])
        []
    """
    return [row.to_json() for row in sorted(rows, key=lambda row: (row.kind, row.id))]
