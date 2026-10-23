#!/usr/bin/env python3
"""Group each class's methods into cohesion clusters (LCOM4), using only the standard library.

Usage:
    python3 lcom4_clusters.py [PATH ...] [--all]

Each PATH is a file or a directory; the default is the current directory.
Directories are searched recursively for ``*.py`` files, skipping dot
directories, ``__pycache__``, ``venv``/``.venv``, ``node_modules`` and
``site-packages``.

Two methods of a class are linked when they touch the same instance attribute
(``self.x``) or when one refers to the other (``self.m()``, or ``self.total``
for a property, which counts as attribute access by name). LCOM4 is the number
of connected groups: 1 means one cohesive responsibility; 2 or more means the
class bundles groups that share no state, and each group is a candidate to
extract into its own class. It is a candidate, not a verdict: a facade or a
mixin can be loosely connected by design.

Left out of the graph: classmethods, staticmethods, stub-only methods (body is
just a docstring, pass, ``...`` or ``raise NotImplementedError``) and dunder
methods such as ``__init__`` or ``__repr__``, which usually touch every field
and would glue unrelated groups together. Protocol classes, and classes left
with fewer than two methods, are skipped.

stdout is a JSON array of objects, sorted by (file, line)::

    {"class": "Outer.Inner", "file": "pkg/mod.py", "line": 12, "lcom4": 2,
     "clusters": [["restock", "in_stock"], ["notify", "welcome"]]}

Clusters are ordered by their first method in the source, and methods inside a
cluster keep source order. Only classes with lcom4 > 1 are listed unless
``--all`` is given.

Exit status: 0 after a scan, with or without findings; 2 on a usage error or a
PATH that does not exist or cannot be read. A file that fails to parse is named
on stderr and skipped.

Example:
    python3 lcom4_clusters.py src/ --all > cohesion.json

``_pyscan_common.py``, beside this script, holds the file walk and AST helpers
it shares with ``detect_smells.py``.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING

# The helper module sits beside this script: find it even under ``python -I`` (no script dir),
# and write no __pycache__ into the synced skill directory.
sys.dont_write_bytecode = True
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _pyscan_common import (  # noqa: E402
    FUNCTION_TYPES,
    is_dunder,
    is_stub_body,
    load_modules,
    receiver_of,
    report_unreadable,
    simple_name,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from _pyscan_common import FunctionNode

PROG = "lcom4_clusters.py"
UNBOUND_DECORATORS = frozenset({"classmethod", "staticmethod"})


@dataclass(frozen=True)
class ClassCohesion:
    """The method clusters of one class."""

    qualname: str
    file: str
    line: int
    clusters: list[list[str]]

    def to_json(self) -> dict[str, object]:
        """The output object for this class."""
        return {
            "class": self.qualname,
            "file": self.file,
            "line": self.line,
            "lcom4": len(self.clusters),
            "clusters": self.clusters,
        }


# --- AST helpers -------------------------------------------------------------------------


def is_protocol(cls: ast.ClassDef) -> bool:
    """True when ``Protocol`` (or ``Protocol[T]``) is among the explicit bases."""
    return any(simple_name(base) == "Protocol" for base in cls.bases)


def is_graph_method(fn: FunctionNode) -> bool:
    """True for a method that belongs in the cohesion graph (see the module docstring)."""
    decorators = {simple_name(decorator) for decorator in fn.decorator_list}
    if decorators & UNBOUND_DECORATORS or is_dunder(fn.name) or receiver_of(fn) is None:
        return False
    return not is_stub_body(fn.body)


def receiver_references(fn: FunctionNode) -> set[str]:
    """Every ``<receiver>.<name>`` the body reads, writes or calls."""
    receiver = receiver_of(fn)
    nodes = (node for stmt in fn.body for node in ast.walk(stmt))
    return {
        node.attr
        for node in nodes
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == receiver
    }


# --- cohesion graph ----------------------------------------------------------------------


def method_references(cls: ast.ClassDef) -> dict[str, set[str]]:
    """Graph methods in source order, each with the receiver names it references.

    A property's getter and setter share a name, so they merge into one node.
    """
    references: dict[str, set[str]] = {}
    for fn in (child for child in cls.body if isinstance(child, FUNCTION_TYPES)):
        if is_graph_method(fn):
            references.setdefault(fn.name, set()).update(receiver_references(fn))
    return references


def links(references: dict[str, set[str]], method_names: set[str]) -> Iterator[tuple[str, str]]:
    """Pairs of graph methods that share an attribute or where one refers to the other.

    Names of any method defined on the class are calls, not shared state, so two
    methods that both call a staticmethod helper are not linked by that alone;
    nor are dunder attributes such as ``self.__class__``, which every object has.
    """
    attributes = {name: shared_state(refs, method_names) for name, refs in references.items()}
    for first, second in combinations(references, 2):
        refers = second in references[first] or first in references[second]
        if refers or attributes[first] & attributes[second]:
            yield first, second


def shared_state(references: set[str], method_names: set[str]) -> set[str]:
    """The referenced names that are instance state: not methods, not dunders."""
    return {name for name in references - method_names if not is_dunder(name)}


def connected_groups(names: list[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Union-find over ``edges``; groups and their members keep the order of ``names``."""
    parent = {name: name for name in names}
    for first, second in edges:
        parent[root_of(parent, first)] = root_of(parent, second)
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(root_of(parent, name), []).append(name)
    return list(groups.values())


def root_of(parent: dict[str, str], name: str) -> str:
    """Representative of ``name``'s group, halving the path as it climbs."""
    while parent[name] != name:
        parent[name] = parent[parent[name]]
        name = parent[name]
    return name


def class_clusters(cls: ast.ClassDef) -> list[list[str]] | None:
    """Method clusters of ``cls``, or None when the class is out of scope."""
    if is_protocol(cls):
        return None
    references = method_references(cls)
    if len(references) < 2:
        return None
    method_names = {child.name for child in cls.body if isinstance(child, FUNCTION_TYPES)}
    return connected_groups(list(references), links(references, method_names))


def qualified_classes(tree: ast.Module) -> Iterator[tuple[str, ast.ClassDef]]:
    """Every class with a ``__qualname__``-style name (``Outer.Inner``, ``f.<locals>.C``).

    Iterative, so a deeply nested expression cannot exhaust the recursion limit.
    """
    stack: list[tuple[ast.AST, str]] = [(tree, "")]
    while stack:
        node, prefix = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                yield prefix + child.name, child
            stack.append((child, child_prefix(child, prefix)))


def child_prefix(node: ast.AST, prefix: str) -> str:
    """The qualname prefix for names defined inside ``node``."""
    if isinstance(node, ast.ClassDef):
        return f"{prefix}{node.name}."
    if isinstance(node, FUNCTION_TYPES):
        return f"{prefix}{node.name}.<locals>."
    return prefix


def module_cohesion(name: str, tree: ast.Module) -> Iterator[ClassCohesion]:
    """One :class:`ClassCohesion` per in-scope class of a parsed module."""
    for qualname, cls in qualified_classes(tree):
        clusters = class_clusters(cls)
        if clusters is not None:
            yield ClassCohesion(qualname, name, cls.lineno, clusters)


# --- files and CLI -----------------------------------------------------------------------


def scan(paths: Sequence[Path], *, include_cohesive: bool = False) -> list[dict[str, object]]:
    """Cohesion report for every class under ``paths``, sorted by (file, line).

    >>> scan([Path("pkg")])  # doctest: +SKIP
    [{'class': 'Shop', 'file': 'pkg/shop.py', 'line': 3, 'lcom4': 2, 'clusters': [...]}]
    """
    modules = load_modules(paths, PROG)
    found = [item for name, tree in modules for item in module_cohesion(name, tree)]
    kept = [item for item in found if include_cohesive or len(item.clusters) > 1]
    kept.sort(key=lambda item: (item.file, item.line, item.qualname))
    return [item.to_json() for item in kept]


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Command-line interface; argparse exits with status 2 on a usage error."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Print the LCOM4 method clusters of Python classes as a JSON array.",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], metavar="PATH", help="file or directory (default: .)"
    )
    parser.add_argument(
        "--all", action="store_true", help="also list cohesive classes (lcom4 == 1)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: scan the given paths and print JSON; returns the exit status."""
    args = parse_args(argv)
    paths = [Path(raw) for raw in args.paths]
    if report_unreadable(paths, PROG):
        return 2
    print(json.dumps(scan(paths, include_cohesive=args.all), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
