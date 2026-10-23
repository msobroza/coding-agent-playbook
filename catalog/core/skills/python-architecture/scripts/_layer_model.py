"""The default layers and the records ``layer_map.py`` passes between its helpers; not run.

Standard library only, Python 3.10 or later, like the script that imports it.
``layer_map.py`` puts its own directory on ``sys.path`` before importing this module,
so it still runs standalone from any working directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Layer -> the space-separated directory (or module) names that put a module in it.
DEFAULT_LAYERS: dict[str, str] = {
    "interface": "api routers routes endpoints views cli",
    "application": "services operations use_cases usecases application",
    "domain": "domain models entities",
    "infrastructure": "db repositories adapters infrastructure infra persistence storage",
}
# Layer -> the space-separated layers it may import besides itself.
DEFAULT_ALLOWED: dict[str, str] = {
    "interface": "application domain",
    "application": "domain",
    "domain": "",
    "infrastructure": "domain application",
}
# The arch-composition-root rule's globs name the same files; a test keeps them equal.
# cli.py is one because a Click or Typer root group builds the services (the rule's
# Good Example); the module still keeps the interface layer for its importers.
ROOT_FILE_NAMES = frozenset(
    {"main.py", "app.py", "__main__.py", "deps.py", "dependencies.py"}
    | {"container.py", "bootstrap.py", "wiring.py", "cli.py"}
)
# The one layer whose modules may import a composition root: a route reads the provider
# module's Annotated aliases. Anything else importing the wiring is a service locator.
ROOT_IMPORTING_LAYER = "interface"
# A package's dotted name split into parts, e.g. ("shop", "routers").
PackagePath = tuple[str, ...]


class UsageError(ValueError):
    """A command-line value the script cannot use; main() turns it into exit status 2."""


@dataclass(frozen=True)
class LayerRules:
    """Which path parts name each layer, and which other layers each one may import."""

    patterns: dict[str, tuple[tuple[str, ...], ...]]
    allowed: dict[str, frozenset[str]]
    root_modules: tuple[str, ...] = ()  # --root-module values as given: names or paths

    def order(self, layer: str) -> int:
        """Position of LAYER in declaration order, so reports list layers stably."""
        return list(self.patterns).index(layer)

    def permits(self, source: str, target: str) -> bool:
        """True when code in layer SOURCE may import code in layer TARGET."""
        return source == target or target in self.allowed.get(source, frozenset())


@dataclass(frozen=True)
class SourceModule:
    """One scanned .py file and the dotted name it is imported under."""

    name: str
    path: Path
    is_package: bool

    @property
    def package(self) -> tuple[str, ...]:
        """The package a relative import inside this module starts from."""
        parts = tuple(self.name.split("."))
        return parts if self.is_package else parts[:-1]


@dataclass(frozen=True)
class RawImport:
    """An import statement's possible targets, most specific first, before resolution."""

    candidates: tuple[str, ...]
    line: int
    type_only: bool
    deferred: bool


@dataclass(frozen=True)
class ImportEdge:
    """One scanned module importing another scanned module."""

    importer: str
    imported: str
    line: int
    type_only: bool
    deferred: bool

    @property
    def at_import_time(self) -> bool:
        """True when the import runs while the importer itself is being imported."""
        return not (self.type_only or self.deferred)
