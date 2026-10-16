"""Which entries of ``.coding-agent-playbook.toml`` ``Config`` owns (SPEC §7.1, §7.2).

``Config`` reads and writes a fixed set of keys; every other entry — ``[links]``,
``[metrics]``, a future table, ``[project] homepage`` — is parsed from the raw
TOML by its own command, or by nothing yet. ``playbook init`` and ``playbook
check --refresh`` rewrite the committed file, so they must carry those entries
over themselves: :func:`unmanaged_config_entries` picks them out of the
committed table and :func:`with_unmanaged_entries` writes them back after the
config's own keys. A leaf module (no engine imports), split from ``config.py``.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The top-level keys :class:`~coding_agent_playbook.config.Config` owns: exactly
#: what ``Config.from_dict`` reads and a fully populated ``Config.to_dict`` writes
#: (pinned against the dataclass fields by ``tests/unit/test_config.py``). Derived
#: ``compare=False`` fields (``deprecated_overlay_names``) are exempt: ``Config``
#: computes them from other fields and never writes them. Every
#: other top-level key is parsed from the raw TOML by its own command and never
#: passes through ``Config``, so a rewrite of the committed file must carry it
#: over itself (:func:`unmanaged_config_entries`; ``playbook init`` and
#: ``playbook check --refresh``, through ``commands/_committed_config``).
CONFIG_MANAGED_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "project",
        "engine",
        "overlays_enabled",
        "adapters_enabled",
        "storage",
        "detector_cache",
        "user_choices",
        "output",
    }
)

#: The managed tables whose keys ``Config`` reads one by one, with those keys:
#: exactly what ``Config.to_dict`` writes in each (pinned against the dataclass
#: fields by ``tests/unit/test_config.py``). Any other key in them
#: (``[project] homepage``) is not ``Config``'s, so a rewrite keeps it. Not listed:
#: ``[detector_cache]`` is regenerated whole (a stale entry must go) and
#: ``[user_choices]`` travels whole inside ``Config``, so each is owned outright.
CONFIG_MANAGED_TABLE_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "project": frozenset({"name", "kind", "description"}),
        "engine": frozenset({"version"}),
        "storage": frozenset({"artifact_source", "state_source"}),
        "output": frozenset({"commit"}),
    }
)


def unmanaged_config_entries(data: Mapping[str, Any]) -> dict[str, Any]:
    """What a decoded config file holds that ``Config`` does not own, to write back as is.

    Every top-level entry outside :data:`CONFIG_MANAGED_KEYS`, plus, under the
    table's name, the unknown keys of a table in :data:`CONFIG_MANAGED_TABLE_KEYS`
    (only when there are some). Values are returned as parsed (not copied), in
    file order, so :func:`with_unmanaged_entries` reproduces them exactly.

    Example::

        >>> unmanaged_config_entries({"schema_version": 1, "links": {"allowed_domains": []},
        ...                           "project": {"name": "x", "homepage": "h"}})
        {'links': {'allowed_domains': []}, 'project': {'homepage': 'h'}}
    """
    entries: dict[str, Any] = {}
    for key, value in data.items():
        if key not in CONFIG_MANAGED_KEYS:
            entries[key] = value
        elif unknown := _unknown_table_keys(key, value):
            entries[key] = unknown
    return entries


def _unknown_table_keys(key: str, value: object) -> dict[str, Any]:
    """The entries of the managed table ``key`` that ``Config`` does not read, else ``{}``."""
    owned = CONFIG_MANAGED_TABLE_KEYS.get(key)
    if owned is None or not isinstance(value, dict):
        return {}
    return {name: item for name, item in value.items() if name not in owned}


def with_unmanaged_entries(
    table: Mapping[str, Any], preserved: Mapping[str, Any]
) -> dict[str, Any]:
    """``table`` (a :meth:`Config.to_dict`) with ``preserved`` written back after its own keys.

    ``preserved`` is :func:`unmanaged_config_entries` of the file being rewritten:
    a top-level entry is added, and a managed table's unknown keys are appended
    to that table. A preserved key ``Config`` owns is refused with a
    ``ValueError`` naming it, so ``table`` alone decides those and an emptied
    list or a dropped description cannot come back from the old file.

    Example::

        >>> with_unmanaged_entries({"project": {"name": "x"}}, {"project": {"homepage": "h"}})
        {'project': {'name': 'x', 'homepage': 'h'}}
    """
    clash = _owned_keys_in(preserved)
    if clash:
        raise ValueError(
            f"preserved entries {clash!r} are managed by Config; pass only keys outside "
            f"{sorted(CONFIG_MANAGED_KEYS)!r}, or unknown keys of "
            f"{sorted(CONFIG_MANAGED_TABLE_KEYS)!r}"
        )
    merged = dict(table)
    for key, value in preserved.items():
        merged[key] = {**merged.get(key, {}), **value} if key in CONFIG_MANAGED_KEYS else value
    return merged


def _owned_keys_in(preserved: Mapping[str, Any]) -> list[str]:
    """The keys (dotted for a table's key) of ``preserved`` that ``Config`` owns, sorted."""
    owned: list[str] = []
    for key, value in preserved.items():
        if key not in CONFIG_MANAGED_KEYS:
            continue
        table_keys = CONFIG_MANAGED_TABLE_KEYS.get(key)
        if table_keys is None or not isinstance(value, dict):
            owned.append(key)
        else:
            owned.extend(f"{key}.{name}" for name in table_keys.intersection(value))
    return sorted(owned)
