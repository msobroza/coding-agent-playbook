"""Build ``layer_map.py``'s layer rules and check modules and imports against them; not run.

Standard library only, Python 3.10 or later, like the script that imports it.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from _layer_model import (
    DEFAULT_ALLOWED,
    DEFAULT_LAYERS,
    ROOT_FILE_NAMES,
    ROOT_IMPORTING_LAYER,
    ImportEdge,
    LayerRules,
    PackagePath,
    SourceModule,
    UsageError,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

_LAYER_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
_PATH_SEPARATOR_RE = re.compile(r"[/\\.]")


# --- the rules from the command line ------------------------------------------------


def build_rules(
    layer_args: Sequence[str], allow_args: Sequence[str], root_args: Sequence[str]
) -> LayerRules:
    """Apply the --layer, --allow and --root-module values on top of the defaults.

    >>> build_rules(["web=http"], ["web=domain"], []).allowed["web"]
    frozenset({'domain'})
    """
    patterns = {
        layer: tuple(map(_path_parts, names.split())) for layer, names in DEFAULT_LAYERS.items()
    }
    allowed = {layer: frozenset(deps.split()) for layer, deps in DEFAULT_ALLOWED.items()}
    for text in layer_args:
        layer, names = _parse_name_values(text, "--layer")
        patterns[layer] = tuple(parts for parts in map(_path_parts, names) if parts)
        allowed.setdefault(layer, frozenset())
    for text in allow_args:
        layer, deps = _parse_name_values(text, "--allow")
        _require_known_layers(text, [layer, *deps], patterns)
        allowed[layer] = frozenset(deps)
    for text in root_args:
        _root_module_name(text)  # fail before scanning on a value that names nothing
    return LayerRules(patterns, allowed, tuple(root_args))


def _path_parts(text: str) -> tuple[str, ...]:
    trimmed = text[:-3] if text.endswith(".py") else text
    return tuple(part for part in _PATH_SEPARATOR_RE.split(trimmed.strip()) if part)


def _parse_name_values(text: str, flag: str) -> tuple[str, list[str]]:
    """Split a NAME=VALUE1,VALUE2 flag value, raising UsageError for any other shape."""
    name, separator, value = text.partition("=")
    name = name.strip()
    if not separator or not _LAYER_NAME_RE.fullmatch(name):
        raise UsageError(f"{flag} expects NAME=VALUE1,VALUE2, got {text!r}")
    return name, [part.strip() for part in value.split(",") if part.strip()]


def _require_known_layers(text: str, names: Sequence[str], patterns: Collection[str]) -> None:
    """Raise UsageError when an --allow value names a layer no rule defines."""
    unknown = [name for name in names if name not in patterns]
    if unknown:
        raise UsageError(
            f"--allow {text!r} names unknown layer(s) {', '.join(unknown)}; "
            f"known layers: {', '.join(patterns)}"
        )


def _root_module_name(text: str) -> str:
    parts = _path_parts(text)
    if not parts:
        raise UsageError(f"--root-module expects a module name or file path, got {text!r}")
    return ".".join(parts)


# --- layers -------------------------------------------------------------------------


def classify(
    module: str, rules: LayerRules, containers: Collection[PackagePath] = frozenset()
) -> str | None:
    """Return the layer of MODULE: the outermost dotted part that names a layer.

    A part that is one of CONTAINERS (see container_packages) is a name, not a layer,
    and is skipped.

    >>> classify("shop.routers.carts", build_rules([], [], []))
    'interface'
    >>> classify("api.db.session", build_rules([], [], []), {("api",)})
    'infrastructure'
    """
    parts = tuple(module.split("."))
    for start in range(len(parts)):
        match = _match_at(parts, start, rules)
        if match is None or _is_container_match(parts, start, match, containers):
            continue
        return match[0]
    return None


def _match_at(parts: PackagePath, start: int, rules: LayerRules) -> tuple[str, int] | None:
    # (layer, pattern length): the longest pattern matching at START wins, and ties go
    # to the layer declared first.
    matches = [
        (len(pattern), layer)
        for layer, patterns in rules.patterns.items()
        for pattern in patterns
        if parts[start : start + len(pattern)] == pattern
    ]
    if not matches:
        return None
    length, layer = max(matches, key=lambda match: match[0])
    return layer, length


def _is_container_match(
    parts: PackagePath, start: int, match: tuple[str, int], containers: Collection[PackagePath]
) -> bool:
    # Only a single-part name can be a container; a multi-part --layer pattern is explicit.
    return match[1] == 1 and parts[: start + 1] in containers


def container_packages(names: Iterable[str], rules: LayerRules) -> frozenset[PackagePath]:
    """Packages named like a layer that are a project's name rather than that layer.

    A package qualifies when the names below it cover at least two other layers and no
    package beside it names another layer: a service packaged as api/ holding
    api/services/ and api/db/. Layer-first packages side by side (api/, db/) stay
    layers, and so does db/ holding only db/models.py and db/repositories.py.

    >>> rules = build_rules([], [], [])
    >>> sorted(container_packages(["api.db.session", "api.services.pay"], rules))
    [('api',)]
    """
    level_layers: dict[PackagePath, set[str]] = defaultdict(set)  # parent -> its children's
    below: dict[PackagePath, set[str]] = defaultdict(set)  # package -> layers named under it
    own: dict[PackagePath, str] = {}  # package -> the layer its own single name matches
    for name in names:
        parts = tuple(name.split("."))
        for start in range(len(parts)):
            match = _match_at(parts, start, rules)
            if match is None:
                continue
            level_layers[parts[:start]].add(match[0])
            for depth in range(1, start + 1):
                below[parts[:depth]].add(match[0])
            if match[1] == 1:
                own[parts[: start + 1]] = match[0]
    return frozenset(
        package
        for package, layer in own.items()
        if level_layers[package[:-1]] == {layer} and len(below[package] - {layer}) >= 2
    )


# --- composition roots --------------------------------------------------------------


def find_roots(
    modules: dict[str, SourceModule], rules: LayerRules, root: Path, scanned: Path
) -> frozenset[str]:
    """The wiring modules, which may import any layer: root file names plus --root-module.

    A --root-module value that looks like a path is also read as a file: absolute, or
    relative to the working directory, ROOT or the SCANNED directory, so the ``file``
    the report prints works. Raises UsageError for a value that matches no module.
    """
    roots = {name for name, module in modules.items() if module.path.name in ROOT_FILE_NAMES}
    resolved = {name: module.path.resolve() for name, module in modules.items()}
    for text in rules.root_modules:
        matched = _modules_named_by(text, resolved, (Path("."), root, scanned))
        if not matched:
            raise UsageError(
                f"--root-module {text!r} matches no scanned module under "
                f"{scanned.as_posix()}; give a dotted module, a trailing part of one, "
                "or the path of a scanned .py file"
            )
        roots |= matched
    return frozenset(roots)


def _modules_named_by(text: str, resolved: dict[str, Path], places: Sequence[Path]) -> set[str]:
    dotted = _root_module_name(text)
    files = _named_files(text, places)
    return {
        name
        for name, path in resolved.items()
        if name == dotted or name.endswith(f".{dotted}") or path in files
    }


def _named_files(text: str, places: Sequence[Path]) -> frozenset[Path]:
    if not (text.endswith(".py") or "/" in text or os.sep in text):
        return frozenset()
    # Joining an absolute TEXT onto a place yields TEXT itself.
    candidates = (place / text for place in places)
    return frozenset(path.resolve() for path in candidates if path.is_file())


# --- checking imports ---------------------------------------------------------------


def breaks_rule(
    edge: ImportEdge, layers: dict[str, str], roots: frozenset[str], rules: LayerRules
) -> bool:
    """True when EDGE breaks a rule.

    That is: it goes from one layer to another the rules do not allow, or a layered
    module outside the interface layer imports a composition root (a service locator).
    """
    source, target = layers.get(edge.importer), layers.get(edge.imported)
    if source is None or edge.importer in roots:
        return False
    if edge.imported in roots and source != ROOT_IMPORTING_LAYER:
        return True
    return target is not None and not rules.permits(source, target)


def layer_flows(
    edges: Iterable[ImportEdge], layers: dict[str, str], roots: frozenset[str], rules: LayerRules
) -> tuple[tuple[str, str, int], ...]:
    """Count distinct runtime module pairs between two different layers, roots left out."""
    pairs = {(e.importer, e.imported) for e in edges if not e.type_only and e.importer not in roots}
    counts = Counter(
        (layers[importer], layers[imported])
        for importer, imported in pairs
        if importer in layers and imported in layers and layers[importer] != layers[imported]
    )
    ordered = sorted(counts, key=lambda pair: (rules.order(pair[0]), rules.order(pair[1])))
    return tuple((source, target, counts[(source, target)]) for source, target in ordered)
