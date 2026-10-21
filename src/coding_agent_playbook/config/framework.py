"""The spec-driven framework a repo chose, and the ``framework.toml`` that marks one (D57, D71).

``playbook init --framework superpowers | mattpocock | none`` writes the committed
``framework`` key. A short name is the ``name`` of a bundled plugin's
``framework.toml``; any other value is the full module name of an overlay package
that ships its own (an organization's framework); ``none`` enables nothing. The
framework's layer joins the enabled layers ahead of ``overlays_enabled``, which
stays for non-framework add-ons (:func:`layers_with_framework`).

``framework.toml`` sits at a bundled plugin's root (``catalog/plugins/<leaf>/``) or
an overlay package's ``resources/`` root and holds ``name``, ``description`` and an
optional ``[layout_aliases]`` table mapping a path prefix the framework's text uses
to a D71 layout key. The skill-to-role tags live on the skills (D77,
``skills.capabilities``), never here.
"""

from __future__ import annotations

import importlib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.roots import (
    bundled_plugins,
    canonical_overlay_name,
    catalog_layer_root,
    is_bundled_layer,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: The metadata file that marks a layer as a spec-driven framework.
FRAMEWORK_FILENAME: Final = "framework.toml"
#: The ``framework`` value (and init answer) that enables no framework; the default.
NO_FRAMEWORK: Final = "none"
#: The document layout keys of D71, in the spec's order; a layout alias maps to one.
LAYOUT_KEYS: Final = (
    "glossary",
    "context_map",
    "adr",
    "architecture",
    "specs",
    "plans",
    "research",
    "agents",
    "scratch",
)
_METADATA_KEYS: Final = ("name", "description", "layout_aliases")


class FrameworkMetadataError(ValueError):
    """A ``framework.toml`` the engine cannot read, with every problem found.

    Example::

        >>> str(FrameworkMetadataError("p/framework.toml", ["unknown key 'x'"]))
        "p/framework.toml: unknown key 'x'"
    """

    def __init__(self, where: str, problems: Sequence[str]) -> None:
        self.where = where
        self.problems = tuple(problems)
        super().__init__("\n".join(f"{where}: {problem}" for problem in problems))


@dataclass(frozen=True)
class FrameworkMetadata:
    """One layer's parsed ``framework.toml``.

    Example: ``read_framework_metadata("coding_agent_playbook.plugins.superpowers").name``
    -> ``"superpowers"``.
    """

    package: str
    name: str
    description: str
    layout_aliases: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


def framework_package(choice: str) -> str | None:
    """The layer package ``choice`` (a ``framework`` value) enables, ``None`` for ``none``.

    A bundled framework's short name resolves to its plugin; anything else is
    taken as a module name (its deprecated ``packs`` spelling canonicalized).

    Example::

        >>> framework_package("superpowers")
        'coding_agent_playbook.plugins.superpowers'
    """
    name = choice.strip()
    if name == NO_FRAMEWORK:
        return None
    return bundled_framework_names().get(name) or canonical_overlay_name(name)


def layers_with_framework(overlays: Sequence[str], framework: str | None) -> list[str]:
    """The enabled layer packages: the framework's first, then ``overlays``, each once.

    Example::

        >>> layers_with_framework(["acme.rules"], "none")
        ['acme.rules']
    """
    package = None if framework is None else framework_package(framework)
    return list(dict.fromkeys([*([package] if package else []), *overlays]))


def bundled_framework_names() -> dict[str, str]:
    """``{framework.toml name: plugin package}`` for each bundled plugin that is a framework.

    A plugin whose ``framework.toml`` does not parse is left out here; validate
    reports it when the plugin is enabled.

    Example::

        >>> bundled_framework_names()["mattpocock"]
        'coding_agent_playbook.plugins.mattpocock_skills'
    """
    names: dict[str, str] = {}
    for package in bundled_plugins():
        try:
            metadata = read_framework_metadata(package)
        except FrameworkMetadataError:
            continue
        if metadata is not None:
            names[metadata.name] = package
    return names


def framework_layers(layers: Iterable[str]) -> list[str]:
    """The packages of ``layers`` that ship a ``framework.toml``, in order.

    Example::

        >>> framework_layers(["coding_agent_playbook", "coding_agent_playbook.plugins.superpowers"])
        ['coding_agent_playbook.plugins.superpowers']
    """
    return [package for package in layers if _metadata_path(package) is not None]


def enabled_framework(layers: Iterable[str]) -> str | None:
    """The framework layer among ``layers`` (the first one; validate refuses two), or ``None``.

    Example::

        >>> enabled_framework(["coding_agent_playbook.plugins.superpowers", "acme.rules"])
        'coding_agent_playbook.plugins.superpowers'
    """
    return next(iter(framework_layers(layers)), None)


def read_framework_metadata(package: str) -> FrameworkMetadata | None:
    """``package``'s ``framework.toml``, or ``None`` when the layer ships none.

    Raises :class:`FrameworkMetadataError` naming the file and every problem.

    Example::

        >>> read_framework_metadata("coding_agent_playbook") is None
        True
    """
    path = _metadata_path(package)
    if path is None:
        return None
    where = f"{package}/{FRAMEWORK_FILENAME}"
    try:
        table = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise FrameworkMetadataError(where, [f"invalid TOML: {exc}"]) from exc
    problems = metadata_problems(table)
    if problems:
        raise FrameworkMetadataError(where, problems)
    aliases = table.get("layout_aliases", {})
    return FrameworkMetadata(
        package=package,
        name=table["name"].strip(),
        description=table["description"].strip(),
        layout_aliases=MappingProxyType(dict(aliases)),
    )


def metadata_problems(table: Mapping[str, object]) -> list[str]:
    """Every reason ``table`` (a decoded ``framework.toml``) is refused; ``[]`` when sound.

    Example::

        >>> metadata_problems({"name": "a", "description": "b"})
        []
    """
    problems = [
        f"unknown key {key!r}; allowed keys: {', '.join(_METADATA_KEYS)}"
        for key in table
        if key not in _METADATA_KEYS
    ]
    for key in ("name", "description"):
        value = table.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{key} must be a non-empty string, got {value!r}")
    problems.extend(_alias_problems(table.get("layout_aliases", {})))
    return problems


def _alias_problems(aliases: object) -> list[str]:
    """Why each ``[layout_aliases]`` entry is refused (D71)."""
    if not isinstance(aliases, Mapping):
        return [f"layout_aliases must be a table of path prefix = layout key, got {aliases!r}"]
    problems: list[str] = []
    for prefix, key in aliases.items():
        if not _is_path_prefix(prefix):
            problems.append(
                f"layout_aliases {prefix!r} is not a path prefix: write a relative "
                "directory path ending with '/', without '..'"
            )
        if key not in LAYOUT_KEYS:
            problems.append(
                f"layout_aliases {prefix!r} maps to unknown layout key {key!r}; "
                f"known keys: {', '.join(LAYOUT_KEYS)}"
            )
    return problems


def _is_path_prefix(prefix: str) -> bool:
    """A relative POSIX directory path ending with ``/``, with no ``..`` or empty segment."""
    if not prefix.endswith("/") or prefix.startswith("/") or "\\" in prefix:
        return False
    parts = PurePosixPath(prefix).parts
    return bool(parts) and ".." not in parts and "//" not in prefix


def _metadata_path(package: str) -> Path | None:
    """``<layer root>/framework.toml`` when that file exists, else ``None``."""
    root = _layer_root(package)
    if root is None:
        return None
    path = root / FRAMEWORK_FILENAME
    return path if path.is_file() else None


def _layer_root(package: str) -> Path | None:
    """A bundled layer's catalog directory, or an overlay package's ``resources/``."""
    if is_bundled_layer(package):
        return catalog_layer_root(package)
    try:
        module = importlib.import_module(package)
    except Exception:  # an overlay's import may raise anything; the preflight reports it
        return None
    for location in getattr(module, "__path__", None) or []:
        resources = Path(location) / "resources"
        if resources.is_dir():
            return resources
    return None
