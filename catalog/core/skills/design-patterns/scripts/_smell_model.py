"""The records and AST helpers behind ``detect_smells.py``; not run on its own.

Standard library only, Python 3.10 or later. Holds the closed set of smell ids,
the candidate record every detector yields, the cross-module class index and
the AST helpers the detectors in ``_smell_detectors.py`` share.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NamedTuple

from _pyscan_common import FUNCTION_TYPES, FunctionNode, simple_name

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

EVIDENCE_WIDTH = 60
# ast.unparse recurses once per nesting level, so a sum of a few hundred terms exhausts the stack.
TOO_DEEP_TO_PRINT = "<expression too deep to print>"
SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
# Bases with no overridable public methods: inheriting them never makes a method an override.
NEUTRAL_BASES = frozenset(
    {"object", "ABC", "Generic", "NamedTuple", "TypedDict"}
    | {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}
)

SmellId = Literal[
    "mutable-default-argument",
    "isinstance-ladder",
    "long-parameter-list",
    "boolean-flag-parameter",
    "bare-except",
    "swallowed-exception",
    "deep-nesting",
    "long-function",
    "method-could-be-function",
    "namespace-class",
    "type-in-name",
    "module-level-mutable-global-rebound",
]


class Candidate(NamedTuple):
    """One smell candidate inside a module (the file is attached by the caller)."""

    smell: SmellId
    line: int
    evidence: str


@dataclass
class ClassIndex:
    """Method and base names of every scanned class, keyed by the bare class name.

    ``overridden`` maps a class to the method names some scanned subclass
    redefines: those are extension points, not helpers. Same-named classes from
    different modules are merged, which only makes the override checks more
    conservative.
    """

    methods: dict[str, set[str]] = field(default_factory=dict)
    bases: dict[str, set[str]] = field(default_factory=dict)
    overridden: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_trees(cls, trees: Iterable[ast.Module]) -> ClassIndex:
        """Index every class definition found in ``trees``."""
        index = cls()
        for node in (n for tree in trees for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            index.methods.setdefault(node.name, set()).update(m.name for m in methods_of(node))
            index.bases.setdefault(node.name, set()).update(base_names(node))
        index.mark_overrides()
        return index

    def mark_overrides(self) -> None:
        """Fill ``overridden`` from every scanned class's scanned ancestors."""
        for name, own in self.methods.items():
            for ancestor in self.scanned_ancestors(name):
                self.overridden.setdefault(ancestor, set()).update(own & self.methods[ancestor])

    def scanned_ancestors(self, name: str) -> set[str]:
        """Every ancestor of ``name`` that was itself scanned (unscanned ones are dropped)."""
        found: set[str] = set()
        pending = list(self.bases.get(name, ()))
        while pending:
            base = pending.pop()
            if base not in found and base in self.methods:
                found.add(base)
                pending.extend(self.bases[base])
        return found

    def ancestor_methods(self, bases: Iterable[str]) -> set[str] | None:
        """Method names defined by any ancestor, or None when an ancestor was not scanned.

        >>> ClassIndex({"Base": {"run"}}, {"Base": set()}).ancestor_methods(["Base"])
        {'run'}
        """
        found: set[str] = set()
        pending, seen = list(bases), set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            if name in self.methods:
                found |= self.methods[name]
                pending.extend(self.bases[name])
            elif not is_neutral_base(name):
                return None
        return found


@dataclass(frozen=True)
class ModuleScan:
    """What every detector receives: one parsed module plus the cross-module class index."""

    tree: ast.Module
    classes: ClassIndex


def decorator_names(node: FunctionNode | ast.ClassDef) -> set[str]:
    """``@abc.abstractmethod`` -> ``abstractmethod``; ``@total.setter`` -> ``setter``."""
    return {simple_name(decorator) for decorator in node.decorator_list}


def base_names(node: ast.ClassDef) -> list[str]:
    """Bare names of the explicit bases (see :func:`simple_name`)."""
    return [simple_name(base) for base in node.bases]


def is_neutral_base(name: str) -> bool:
    """True for bases that contribute no method a subclass would override."""
    candidate = getattr(builtins, name, None)
    is_exception = isinstance(candidate, type) and issubclass(candidate, BaseException)
    return name in NEUTRAL_BASES or is_exception


def methods_of(node: ast.ClassDef) -> list[FunctionNode]:
    """Functions defined directly in the class body, in source order."""
    return [child for child in node.body if isinstance(child, FUNCTION_TYPES)]


def functions_in(tree: ast.AST) -> Iterator[FunctionNode]:
    """Every function and method anywhere in ``tree``."""
    return (node for node in ast.walk(tree) if isinstance(node, FUNCTION_TYPES))


def classes_in(tree: ast.AST) -> Iterator[ast.ClassDef]:
    """Every class anywhere in ``tree``."""
    return (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Nodes inside ``scope``, not descending into nested functions, classes or lambdas."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, SCOPE_TYPES):
            stack.extend(ast.iter_child_nodes(node))


def snippet(node: ast.AST) -> str:
    """Source text of ``node``, cut to EVIDENCE_WIDTH characters.

    An expression too deep for ``ast.unparse`` yields TOO_DEEP_TO_PRINT, so the
    candidate is still reported.
    """
    try:
        text = ast.unparse(node)
    except RecursionError:
        return TOO_DEEP_TO_PRINT
    return text if len(text) <= EVIDENCE_WIDTH else text[: EVIDENCE_WIDTH - 3] + "..."


def defaults_by_param(args: ast.arguments) -> Iterator[tuple[ast.arg, ast.expr]]:
    """Pair each parameter that has a default with that default."""
    positional = args.posonlyargs + args.args
    with_default = positional[len(positional) - len(args.defaults) :]
    yield from zip(with_default, args.defaults, strict=True)
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        if default is not None:
            yield arg, default
