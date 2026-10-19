"""The layer resource roots: package-relative ids and their directories on this machine.

``guard_config.json``'s ``protected.resource_roots`` lists ``pkg:<package>/resources``
ids for the engine and every ``overlays_enabled`` layer (bundled plugins included):
machine-independent, so ``sync --check`` byte-compares them. ``machine.json``
(written at sync, never committed) maps each id to its absolute directory, which
the runtime reads instead of an absolute path in the committed file. The id keeps
that spelling for every layer: an overlay package's id names its ``resources/``, a
bundled layer's names its directory in the catalog (``catalog/core/``,
``catalog/plugins/<leaf>/``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.config.schema import RESOURCE_ROOT_ID_FORMAT

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["resolve_resource_roots", "resource_root_ids"]


def resource_root_ids(packages: Iterable[str]) -> list[str]:
    """``pkg:<package>/resources`` for each layer package, in layer order, deduplicated.

    Example::

        >>> resource_root_ids(["coding_agent_playbook"])
        ['pkg:coding_agent_playbook/resources']
    """
    return list(dict.fromkeys(RESOURCE_ROOT_ID_FORMAT.format(package=p) for p in packages))


def resolve_resource_roots(packages: Iterable[str]) -> dict[str, str]:
    """``machine.json``'s ``resource_roots``: each id's absolute layer dir on this machine.

    An overlay package resolves to its ``resources/`` through
    ``importlib.resources``; one that cannot be imported, or ships no
    ``resources/``, is left out (the preflight already refused such an
    overlay). A bundled layer (the engine, a bundled plugin) resolves to its
    directory in the catalog and is never imported; an unknown plugin
    leaf is left out the same way. Sync-time only.

    Example::

        >>> resolve_resource_roots(["coding_agent_playbook"])  # doctest: +SKIP
        {'pkg:coding_agent_playbook/resources': '/v/site-packages/coding_agent_playbook/_catalog/core'}
    """
    found: dict[str, str] = {}
    for package in dict.fromkeys(packages):
        root = _layer_dir(package)
        if root is not None:
            found[RESOURCE_ROOT_ID_FORMAT.format(package=package)] = root
    return found


def _layer_dir(package: str) -> str | None:
    """The directory holding ``package``'s kind dirs, or ``None`` when it has none."""
    from importlib import resources

    from coding_agent_playbook.catalog.roots import catalog_layer_root, is_bundled_layer

    if is_bundled_layer(package):
        bundled = catalog_layer_root(package)
        return str(bundled) if bundled is not None and bundled.is_dir() else None
    try:
        root = resources.files(package).joinpath("resources")
    except Exception:  # an overlay's import may raise anything; it is skipped
        return None
    return str(root) if root.is_dir() else None
