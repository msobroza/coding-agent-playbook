#!/usr/bin/env python3
"""Sort a Python project's modules into layers and flag imports that point the wrong way.

Usage:
    python3 layer_map.py [ROOT] [--layer NAME=DIR1,DIR2 ...] [--allow NAME=DEP1,DEP2 ...]
                         [--root-module NAME ...] [--json]

Scans ROOT (default ".", or ROOT/src when that holds Python files) with ast; nothing is
imported or run. Hidden directories, __pycache__, venv, node_modules, site-packages and
test code (tests/, test/, test_*.py, *_test.py, conftest.py) are skipped.

A module's layer is the first (outermost) part of its dotted path that names a layer,
so shop/routers/carts.py and shop/routers.py are both interface code. A module that
matches nothing is unlayered and never checked. The defaults, and what each layer may
import besides itself:

    interface       api routers routes endpoints views cli      -> application, domain
    application     services operations use_cases usecases application   -> domain
    domain          domain models entities                      -> nothing
    infrastructure  db repositories adapters infrastructure infra persistence storage
                                                                -> application, domain

One exception: a container package is a name, not a layer. That is a package named
like a layer that holds packages or modules named after at least two other layers,
while no package beside it names another layer: a project packaged as api/ with
api/services/ and api/db/ inside, or the services/ package that encloses
ROOT=services/billing when that holds domain/ and db/.
Its own name is skipped, so api/db/session.py is infrastructure and api/config.py is
unlayered. Layer-first packages side by side (api/, services/, db/) stay layers. A
name with "/" is never a container, so adding api/models to a layer overrules one.

--layer NAME=DIR1,DIR2 replaces one layer's names or adds a layer (a name with "/",
such as shop/http, matches that run of path parts). --allow NAME=DEP1,DEP2 replaces
what one layer may import; a layer added without --allow may import only itself.
Repeat either flag once per layer.

Composition roots may import any layer: main.py, app.py, __main__.py, deps.py,
dependencies.py, container.py, bootstrap.py, wiring.py, and each --root-module NAME
(a dotted module, a trailing part of one, or the path of a scanned file, absolute or
relative to the working directory, ROOT or the scanned directory). Only interface
modules may import a composition root (the provider module's aliases); any other
layered module that imports one is a rule violation, a service locator.

Absolute and relative imports are resolved to scanned modules; all others are ignored.
Imports under "if TYPE_CHECKING:" never fail the run; the ones that would break a rule
are listed under type_only. A cycle is a group of modules that import one another at
import time: module-level runtime imports, without type-only imports or imports made
inside a function body.

Output is text by default. --json prints one object: layers {module: layer}, flows
[[from_layer, to_layer, module_pairs]], violations [{importer, imported, from_layer,
to_layer, file, line}] (to_layer is null for an unlayered composition root), cycles
[[module, ...]], type_only (shaped like violations), plus scanned, rules,
composition_roots, container_packages and unlayered. Flows count distinct module
pairs between two different layers, composition roots left out.

Exit status: 0 nothing found, 1 a rule violation or an import cycle, 2 usage error,
including a --root-module that matches no scanned module and a ROOT with no module
to scan. Unreadable or unparseable files are reported on stderr and skipped. Findings
are candidates, not verdicts: layers are guessed from names, so confirm each one.

Examples:
    python3 layer_map.py
    python3 layer_map.py services/billing --json
    python3 layer_map.py . --layer interface=http,cli --allow infrastructure=domain
    python3 layer_map.py . --root-module shop.wiring

Standard library only; Python 3.10 or newer.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator, Sequence

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
ROOT_FILE_NAMES = frozenset(
    {"main.py", "app.py", "__main__.py", "deps.py", "dependencies.py"}
    | {"container.py", "bootstrap.py", "wiring.py"}
)
# The one layer whose modules may import a composition root: a route reads the provider
# module's Annotated aliases. Anything else importing the wiring is a service locator.
ROOT_IMPORTING_LAYER = "interface"
# Test code wires its own fakes, like a composition root, so it is not mapped.
SKIPPED_DIR_NAMES = frozenset({"__pycache__", "venv", "node_modules", "site-packages"})
TEST_DIR_NAMES = frozenset({"tests", "test"})
_LAYER_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
_PATH_SEPARATOR_RE = re.compile(r"[/\\.]")
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


@dataclass(frozen=True)
class LayerReport:
    """Everything the text and JSON renderers print."""

    scanned: Path
    rules: LayerRules
    paths: dict[str, Path]
    layers: dict[str, str]
    roots: tuple[str, ...]
    containers: tuple[str, ...]
    unlayered: tuple[str, ...]
    flows: tuple[tuple[str, str, int], ...]
    violations: tuple[ImportEdge, ...]
    type_only: tuple[ImportEdge, ...]
    cycles: tuple[tuple[str, ...], ...]

    @property
    def found_problems(self) -> bool:
        """True when the run should exit 1: a rule violation or an import cycle."""
        return bool(self.violations or self.cycles)


# --- discovering modules ------------------------------------------------------------


def scan_base(root: Path) -> Path:
    """Return ROOT/src when it holds Python source (src layout), else ROOT itself.

    A src/ with no Python, such as a maturin src/lib.rs or a JavaScript src/, would
    otherwise hide the package beside it behind an empty, clean-looking scan.
    """
    src = root / "src"
    if src.is_dir() and next(iter_python_files(src), None) is not None:
        return src
    return root


def iter_python_files(base: Path) -> Iterator[Path]:
    """Yield every non-test .py file under BASE in a stable order."""
    for directory, subdirs, files in os.walk(base):
        subdirs[:] = sorted(name for name in subdirs if not _is_skipped_dir(name))
        yield from (Path(directory) / name for name in sorted(files) if _is_source_file(name))


def _is_skipped_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIPPED_DIR_NAMES or name in TEST_DIR_NAMES


def _is_source_file(name: str) -> bool:
    if not name.endswith(".py") or name == "conftest.py":
        return False
    return not (name.startswith("test_") or name.endswith("_test.py"))


def discover_modules(base: Path) -> dict[str, SourceModule]:
    """Map each dotted module name under BASE to its file; a package beats a same-named file."""
    prefix = _package_prefix(base)
    modules: dict[str, SourceModule] = {}
    for path in iter_python_files(base):
        module = _source_module(path, base, prefix)
        if module is not None and (module.name not in modules or module.is_package):
            modules[module.name] = module
    return modules


def _package_prefix(base: Path) -> tuple[str, ...]:
    # When BASE is itself inside a package (it holds an __init__.py), its modules are
    # imported under the enclosing package names, e.g. ROOT=shop gives "shop.carts".
    prefix: list[str] = []
    current = base.resolve()
    while (current / "__init__.py").is_file() and current.parent != current:
        prefix.insert(0, current.name)
        current = current.parent
    return tuple(prefix)


def _source_module(path: Path, base: Path, prefix: tuple[str, ...]) -> SourceModule | None:
    parts = (*prefix, *path.relative_to(base).with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return SourceModule(".".join(parts), path, is_package) if parts else None


# --- reading imports ----------------------------------------------------------------


def parse_module(path: Path) -> ast.Module | None:
    """Parse PATH, or report it on stderr and return None when it cannot be read or parsed."""
    try:
        source = path.read_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # e.g. SyntaxWarning for "\d" in a plain string
            return ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError, RecursionError) as error:
        print(f"layer_map.py: skipped {path.as_posix()}: {error}", file=sys.stderr)
        return None


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _absolute_base(node: ast.ImportFrom, package: tuple[str, ...]) -> str | None:
    # A relative import climbs (level - 1) packages from the importer's own package;
    # climbing past the top is an error in Python too, so it resolves to nothing.
    if node.level == 0:
        return node.module
    if node.level > len(package):
        return None
    parts = package[: len(package) - node.level + 1]
    return ".".join((*parts, node.module)) if node.module else ".".join(parts)


@dataclass(frozen=True)
class _ImportScope:
    """Whether imports at one point of a module are type-only, or deferred by a function."""

    type_only: bool = False
    deferred: bool = False


def collect_imports(tree: ast.Module, package: tuple[str, ...]) -> list[RawImport]:
    """Every import in TREE, in source order, marked type-only or deferred where it is.

    Iterative, so a long if/elif chain or a deeply nested expression that ast.parse
    accepts cannot exhaust the recursion limit and abort the whole scan.

    >>> [raw.candidates for raw in collect_imports(ast.parse("import a.b"), ())]
    [('a.b',)]
    """
    found: list[RawImport] = []
    stack: list[tuple[ast.AST, _ImportScope]] = [(tree, _ImportScope())]
    while stack:
        node, scope = stack.pop()
        found.extend(_raw_imports(node, package, scope))
        stack.extend(reversed(_scoped_children(node, scope)))
    return found


def _scoped_children(node: ast.AST, scope: _ImportScope) -> list[tuple[ast.AST, _ImportScope]]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _with_scope(node.body, _ImportScope(scope.type_only, deferred=True))
    if isinstance(node, ast.If) and _is_type_checking(node.test):
        guarded = _ImportScope(type_only=True, deferred=scope.deferred)
        # The else branch of `if TYPE_CHECKING:` runs normally.
        return _with_scope(node.body, guarded) + _with_scope(node.orelse, scope)
    return _with_scope(ast.iter_child_nodes(node), scope)


def _with_scope(
    nodes: Iterable[ast.AST], scope: _ImportScope
) -> list[tuple[ast.AST, _ImportScope]]:
    return [(node, scope) for node in nodes]


def _raw_imports(node: ast.AST, package: tuple[str, ...], scope: _ImportScope) -> list[RawImport]:
    targets: list[tuple[str, ...]]
    if isinstance(node, ast.Import):
        targets = [(alias.name,) for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        targets = _from_targets(node, package)
    else:
        return []
    return [RawImport(target, node.lineno, scope.type_only, scope.deferred) for target in targets]


def _from_targets(node: ast.ImportFrom, package: tuple[str, ...]) -> list[tuple[str, ...]]:
    base = _absolute_base(node, package)
    if base is None:
        return []
    return [(base,) if a.name == "*" else (f"{base}.{a.name}", base) for a in node.names]


def resolve_import(candidates: tuple[str, ...], known: Collection[str]) -> str | None:
    """Return the most specific scanned module an import loads, or None for outside code.

    ``from shop import carts`` gives ("shop.carts", "shop"): the submodule wins when it
    exists. Otherwise the longest scanned prefix of the last candidate is used, because
    importing ``shop.carts.view`` also runs ``shop.carts``.

    >>> resolve_import(("shop.carts", "shop"), {"shop", "shop.carts"})
    'shop.carts'
    """
    if len(candidates) > 1 and candidates[0] in known:
        return candidates[0]
    parts = candidates[-1].split(".")
    prefixes = (".".join(parts[:size]) for size in range(len(parts), 0, -1))
    return next((name for name in prefixes if name in known), None)


def module_edges(
    module: SourceModule, tree: ast.Module, known: Collection[str]
) -> list[ImportEdge]:
    """Resolve every import in MODULE's TREE to scanned modules, without duplicates."""
    edges: dict[ImportEdge, None] = {}
    for raw in collect_imports(tree, module.package):
        target = resolve_import(raw.candidates, known)
        if target is not None and target != module.name:
            edges[ImportEdge(module.name, target, raw.line, raw.type_only, raw.deferred)] = None
    return list(edges)


def collect_edges(modules: dict[str, SourceModule]) -> list[ImportEdge]:
    """Every import between scanned modules; unparseable files contribute none."""
    edges: list[ImportEdge] = []
    for module in modules.values():
        tree = parse_module(module.path)
        if tree is not None:
            edges.extend(module_edges(module, tree, modules))
    return edges


# --- layers and rules ---------------------------------------------------------------


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


# --- import cycles ------------------------------------------------------------------


def import_time_graph(modules: Iterable[str], edges: Iterable[ImportEdge]) -> dict[str, set[str]]:
    """Adjacency sets of the imports that run while a module is being imported."""
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for edge in edges:
        if edge.at_import_time:
            graph[edge.importer].add(edge.imported)
    return graph


def find_cycles(graph: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    """Return every group of two or more modules that reach one another, each sorted.

    Kosaraju's strongly connected components, iterative so deep graphs cannot overflow.

    >>> find_cycles({"a": {"b"}, "b": {"a"}, "c": {"a"}})
    (('a', 'b'),)
    """
    reverse = _reverse(graph)
    assigned: set[str] = set()
    groups: list[tuple[str, ...]] = []
    for node in reversed(_finish_order(graph)):
        if node in assigned:
            continue
        group = _reachable(node, reverse, assigned)
        assigned |= group
        if len(group) > 1:
            groups.append(tuple(sorted(group)))
    return tuple(sorted(groups))


def _reverse(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {node: set() for node in graph}
    for node, targets in graph.items():
        for target in targets:
            reverse[target].add(node)
    return reverse


def _finish_order(graph: dict[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for start in sorted(graph):
        if start not in seen:
            seen.add(start)
            _depth_first(start, graph, seen, order)
    return order


def _depth_first(start: str, graph: dict[str, set[str]], seen: set[str], order: list[str]) -> None:
    stack: list[tuple[str, Iterator[str]]] = [(start, iter(sorted(graph[start])))]
    while stack:
        node, children = stack[-1]
        child = next((name for name in children if name not in seen), None)
        if child is None:
            stack.pop()
            order.append(node)
            continue
        seen.add(child)
        stack.append((child, iter(sorted(graph[child]))))


def _reachable(start: str, graph: dict[str, set[str]], excluded: set[str]) -> set[str]:
    found = {start}
    stack = [start]
    while stack:
        fresh = graph[stack.pop()] - found - excluded
        found |= fresh
        stack.extend(fresh)
    return found


# --- the report ---------------------------------------------------------------------


def build_report(root: Path, rules: LayerRules) -> LayerReport:
    """Scan ROOT (or ROOT/src) and check every import against RULES.

    Raises UsageError when nothing is left to scan or a --root-module matches nothing.
    """
    scanned = scan_base(root)
    modules = discover_modules(scanned)
    if not modules:
        raise UsageError(
            f"found no Python module to scan under {scanned.as_posix()} (test code, hidden "
            "and vendored directories are skipped); pass the project or package directory"
        )
    roots = find_roots(modules, rules, root, scanned)
    containers = container_packages(modules, rules)
    layers = {n: layer for n in sorted(modules) if (layer := classify(n, rules, containers))}
    edges = collect_edges(modules)
    crossing = [edge for edge in edges if breaks_rule(edge, layers, roots, rules)]
    paths = {name: module.path for name, module in modules.items()}
    return LayerReport(
        scanned=scanned,
        rules=rules,
        paths=paths,
        layers=layers,
        roots=tuple(sorted(roots)),
        containers=tuple(sorted(".".join(package) for package in containers)),
        unlayered=tuple(sorted(set(modules) - set(layers))),
        flows=layer_flows(edges, layers, roots, rules),
        violations=_by_location([edge for edge in crossing if not edge.type_only], paths),
        type_only=_by_location([edge for edge in crossing if edge.type_only], paths),
        cycles=find_cycles(import_time_graph(modules, edges)),
    )


def _by_location(edges: list[ImportEdge], paths: dict[str, Path]) -> tuple[ImportEdge, ...]:
    return tuple(sorted(edges, key=lambda e: (paths[e.importer].as_posix(), e.line, e.imported)))


def to_json(report: LayerReport) -> dict[str, object]:
    """The --json payload; see the module docstring for its keys."""
    return {
        "scanned": report.scanned.as_posix(),
        "layers": report.layers,
        "flows": [list(flow) for flow in report.flows],
        "violations": [_edge_json(edge, report) for edge in report.violations],
        "cycles": [list(group) for group in report.cycles],
        "type_only": [_edge_json(edge, report) for edge in report.type_only],
        "rules": {
            layer: sorted(deps, key=report.rules.order)
            for layer, deps in report.rules.allowed.items()
        },
        "composition_roots": list(report.roots),
        "container_packages": list(report.containers),
        "unlayered": list(report.unlayered),
    }


def _edge_json(edge: ImportEdge, report: LayerReport) -> dict[str, object]:
    return {
        "importer": edge.importer,
        "imported": edge.imported,
        "from_layer": report.layers.get(edge.importer),
        "to_layer": report.layers.get(edge.imported),
        "file": report.paths[edge.importer].as_posix(),
        "line": edge.line,
    }


def render_text(report: LayerReport) -> str:
    """The human-readable report printed without --json."""
    sections = (
        _summary_text(report),
        _rules_text(report.rules),
        _layers_text(report),
        _flows_text(report),
        _edges_text("Rule violations", report.violations, report),
        _cycles_text(report.cycles),
        _edges_text(
            "Type-only imports (TYPE_CHECKING) that would break a rule, not failing",
            report.type_only,
            report,
        ),
        _closing_text(report),
    )
    return "\n\n".join(sections)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _summary_text(report: LayerReport) -> str:
    return (
        f"Layer map of {report.scanned.as_posix()}: {_plural(len(report.paths), 'module')}, "
        f"{len(report.layers)} layered, {len(report.unlayered)} unlayered, "
        f"{_plural(len(report.roots), 'composition root')}"
    )


def _rules_text(rules: LayerRules) -> str:
    width = max((len(layer) for layer in rules.patterns), default=0)
    lines = ["Rules (every layer may also import itself)"]
    for layer in rules.patterns:
        deps = sorted(rules.allowed.get(layer, frozenset()), key=rules.order)
        lines.append(f"  {layer.ljust(width)} -> {', '.join(deps) or 'nothing'}")
    return "\n".join(lines)


def _layers_text(report: LayerReport) -> str:
    lines = ["Layers"]
    for layer, patterns in report.rules.patterns.items():
        members = [module for module, name in report.layers.items() if name == layer]
        names = ", ".join("/".join(pattern) for pattern in patterns) or "no names"
        lines.append(f"  {layer} ({names}): {_plural(len(members), 'module')}")
        lines.extend(f"    {member}" for member in members)
    lines.append(f"  unlayered, not checked: {_plural(len(report.unlayered), 'module')}")
    lines.append(f"  composition roots, may import any layer: {', '.join(report.roots) or 'none'}")
    if report.containers:
        names = ", ".join(report.containers)
        lines.append(f"  container packages (named like a layer, holding other layers): {names}")
    return "\n".join(lines)


def _flows_text(report: LayerReport) -> str:
    lines = ["Flows between layers (distinct module pairs, composition roots left out)"]
    for source, target, count in report.flows:
        note = "" if report.rules.permits(source, target) else "  (breaks a rule)"
        lines.append(f"  {source} -> {target}: {count}{note}")
    if not report.flows:
        lines.append("  none")
    return "\n".join(lines)


def _edges_text(title: str, edges: Sequence[ImportEdge], report: LayerReport) -> str:
    lines = [f"{title}: {len(edges)}"]
    for edge in edges:
        where = f"{report.paths[edge.importer].as_posix()}:{edge.line}"
        source, target = report.layers[edge.importer], _target_label(edge.imported, report)
        lines.append(f"  {where}  {edge.importer} [{source}] imports {edge.imported} [{target}]")
    return "\n".join(lines)


def _target_label(module: str, report: LayerReport) -> str:
    # An imported composition root may have no layer of its own (a top-level deps.py).
    layer = report.layers.get(module)
    if module not in report.roots:
        return layer or "unlayered"
    return f"{layer}, composition root" if layer else "composition root"


def _cycles_text(cycles: Sequence[tuple[str, ...]]) -> str:
    lines = [f"Import cycles (modules that import one another at import time): {len(cycles)}"]
    lines.extend(f"  {', '.join(group)}" for group in cycles)
    return "\n".join(lines)


def _closing_text(report: LayerReport) -> str:
    if not report.found_problems:
        return "No rule violations or import cycles found."
    return (
        f"Found {_plural(len(report.violations), 'rule violation')} and "
        f"{_plural(len(report.cycles), 'import cycle')}. These are candidates: the layer map "
        "is inferred from directory names, so confirm each one, or describe the project "
        "with --layer, --allow and --root-module."
    )


# --- command line -------------------------------------------------------------------


def _path_parts(text: str) -> tuple[str, ...]:
    trimmed = text[:-3] if text.endswith(".py") else text
    return tuple(part for part in _PATH_SEPARATOR_RE.split(trimmed.strip()) if part)


def _assignment(text: str, flag: str) -> tuple[str, list[str]]:
    name, separator, value = text.partition("=")
    name = name.strip()
    if not separator or not _LAYER_NAME_RE.fullmatch(name):
        raise UsageError(f"{flag} expects NAME=VALUE1,VALUE2, got {text!r}")
    return name, [part.strip() for part in value.split(",") if part.strip()]


def _known_layers(text: str, names: Sequence[str], patterns: Collection[str]) -> None:
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
        layer, names = _assignment(text, "--layer")
        patterns[layer] = tuple(parts for parts in map(_path_parts, names) if parts)
        allowed.setdefault(layer, frozenset())
    for text in allow_args:
        layer, deps = _assignment(text, "--allow")
        _known_layers(text, [layer, *deps], patterns)
        allowed[layer] = frozenset(deps)
    for text in root_args:
        _root_module_name(text)  # fail before scanning on a value that names nothing
    return LayerRules(patterns, allowed, tuple(root_args))


def _existing_dir(text: str) -> Path:
    path = Path(text)
    if path.is_dir():
        return path
    hint = " (repeat --layer/--allow once per NAME=VALUE pair)" if "=" in text else ""
    raise UsageError(f"ROOT must be a directory, got {text!r}{hint}")


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface described in the module docstring."""
    parser = argparse.ArgumentParser(
        prog="layer_map.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("root", nargs="?", default=".", metavar="ROOT")
    parser.add_argument("--layer", action="append", default=[], metavar="NAME=DIR1,DIR2")
    parser.add_argument("--allow", action="append", default=[], metavar="NAME=DEP1,DEP2")
    parser.add_argument("--root-module", action="append", default=[], metavar="NAME")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; return 0 (clean) or 1 (violation or cycle). Usage errors exit 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = _existing_dir(args.root)
        rules = build_rules(args.layer, args.allow, args.root_module)
        report = build_report(root, rules)
    except UsageError as error:
        parser.error(str(error))
    print(json.dumps(to_json(report), indent=2) if args.json else render_text(report))
    return 1 if report.found_problems else 0


if __name__ == "__main__":
    sys.exit(main())
