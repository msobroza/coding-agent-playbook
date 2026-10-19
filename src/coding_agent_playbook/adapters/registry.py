"""Adapter discovery through the ``coding_agent_playbook.adapters`` entry-point group.

- :func:`discover_adapters` — instantiate every enabled adapter, plus the
  always-on ``agents_md`` (SPEC §4.3).
- :func:`installed_output_locations` — what every installed adapter writes or
  once wrote, the bound of the leftover policy (SPEC §4.2 step 9).

The engine never instantiates an adapter directly: everything goes through the
entry-point group, so an out-of-tree adapter is found the same way as a built-in.
Split out of the sync orchestration module in A5 (specs/prT-package-layout.md 4.9).
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.config.model import Config
    from coding_agent_playbook.rendering.rule_registry import RuleRegistry


def discover_adapters(
    config: Config,
    *,
    rule_registry: RuleRegistry | None = None,
) -> dict[str, Adapter]:
    """Discover enabled adapters via the ``coding_agent_playbook.adapters``
    entry-point group.

    The returned mapping is ``name -> instance``. ``agents_md`` is always
    included (SPEC §4.3). Adapters that accept ``rule_registry`` get it; those
    that don't (currently ``agents_md`` and ``shared_skills``) are constructed
    with no arguments. The ``TypeError`` fallback is the canonical idiom for handling
    the two adapter signatures uniformly.
    """
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    enabled = set(config.adapters_enabled) | {"agents_md"}
    discovered: dict[str, Adapter] = {}
    for ep in eps:
        if ep.name not in enabled:
            continue
        cls = ep.load()
        try:
            discovered[ep.name] = cls(rule_registry=rule_registry)
        except TypeError:
            discovered[ep.name] = cls()
    return discovered


def installed_output_locations() -> tuple[str, ...]:
    """Every current and retired output location of an installed adapter, enabled or not.

    Disabled adapters count: their earlier output is exactly what ``playbook
    sync`` must still be able to clean up (SPEC §4.2 step 9). So do retired
    locations (``retired_output_locations``, e.g. the pre-v0.21 ``shared_skills/``):
    the first sync after an upgrade settles the tree an older engine wrote. An
    adapter whose entry point fails to load declares nothing, so its output is
    never deleted.

    Example::

        >>> "shared_skills/" in installed_output_locations()  # doctest: +SKIP
        True
    """
    locations: list[str] = []
    for ep in metadata.entry_points(group="coding_agent_playbook.adapters"):
        try:
            cls = ep.load()
        except (ImportError, AttributeError):
            continue
        locations.extend(getattr(cls, "output_locations", ()))
        locations.extend(getattr(cls, "retired_output_locations", ()))
    return tuple(locations)
