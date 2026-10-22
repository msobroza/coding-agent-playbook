"""Find the modules ``layer_map.py`` scans and the imports between them; not run on its own.

Standard library only, Python 3.10 or later, like the script that imports it.
The file walk and the warning-free parse restate design-patterns' ``_pyscan_common.py``
on purpose: each skill's scripts stay self-contained (ADR 0004), so a fix to one copy
is checked against the other.
"""

from __future__ import annotations

import ast
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from _layer_model import ImportEdge, RawImport, SourceModule

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator

# Test code wires its own fakes, like a composition root, so it is not mapped.
SKIPPED_DIR_NAMES = frozenset({"__pycache__", "venv", "node_modules", "site-packages"})
TEST_DIR_NAMES = frozenset({"tests", "test"})


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
