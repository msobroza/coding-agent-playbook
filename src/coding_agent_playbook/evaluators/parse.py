"""Single shared AST parse layer for static evaluators (SPEC prM §A/§B).

Source is parsed **once** into a :class:`ModuleModel`; every static evaluator
reads that model instead of re-walking the tree. This module also owns the one
canonical :func:`_cyclomatic` helper (used by both the cyclomatic-complexity and
WMC builtins - one source of truth) and the stable scope-key naming
(``<label>::<qualname>`` for a fn/method/class, ``<label>`` for the file).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from coding_agent_playbook.evaluators.scope import Scope

#: AST node types that each contribute one decision point on their own.
_DECISION_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Assert,
    ast.comprehension,
    ast.match_case,
)


def scope_key(label: str, qualname: str | None) -> str:
    """Build a stable scope key: ``<label>::<qualname>`` or ``<label>`` (file)."""
    return label if qualname is None else f"{label}::{qualname}"


def _cyclomatic(node: ast.AST) -> int:
    """Cyclomatic complexity of one function/method body.

    ``1 + decision points``. Decision points are ``If``/``For``/``AsyncFor``/
    ``While``, comprehension ``if`` clauses, ``BoolOp`` operands - 1, each
    ``ExceptHandler``, ``IfExp``, ``match`` ``case`` guards, and ``assert``.
    A bare ``match_case`` with no guard contributes nothing; a guarded one adds
    one for the guard. The walk does **not** descend into nested function or
    class definitions so each callable is measured locally (and WMC can sum the
    per-method values independently).
    """
    complexity = 1
    for child in _walk_local(node):
        if isinstance(child, ast.match_case):
            if child.guard is not None:
                complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, _DECISION_NODES):
            complexity += 1
    return complexity


def _walk_local(node: ast.AST) -> list[ast.AST]:
    """Yield every descendant of ``node`` *except* the bodies of nested
    function/class definitions (those are separate scopes)."""
    collected: list[ast.AST] = []
    # Start from the direct children of the function body, never the def node
    # itself, so a function does not count its own signature decorators etc.
    stack: list[ast.AST] = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        collected.append(current)
        if isinstance(
            current,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            # Do not descend into a nested scope's body.
            continue
        stack.extend(ast.iter_child_nodes(current))
    return collected


@dataclass
class FunctionScope:
    """A function or method, with its precomputed cyclomatic complexity."""

    qualname: str
    scope: Scope
    complexity: int
    scope_key: str


@dataclass
class ClassScope:
    """A class with its resolved base names, direct methods, and its AST node.

    ``node`` is retained so the cohesion/coupling builtins (LCOM4, CBO) can
    re-walk the class body without re-parsing the module.
    """

    qualname: str
    bases: list[str]
    node: ast.ClassDef
    methods: list[FunctionScope] = field(default_factory=list)
    scope_key: str = ""


@dataclass
class ModuleModel:
    """The parsed view of one source file shared by all static evaluators."""

    label: str
    tree: ast.Module
    source: str
    functions: list[FunctionScope] = field(default_factory=list)
    classes: list[ClassScope] = field(default_factory=list)


def _base_name(node: ast.expr) -> str:
    """Best-effort dotted name for a base-class expression (``a.B`` -> ``a.B``)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_base_name(node.value)}.{node.attr}"
    return ast.unparse(node)


def parse_module(source: str, label: str) -> ModuleModel:
    """Parse ``source`` into a :class:`ModuleModel` labelled ``label``.

    Raises :exc:`SyntaxError` on unparseable input (the caller decides whether
    to skip the file). The model records every function/method (with cyclomatic
    complexity) and every class (with base names + its direct methods).
    """
    tree = ast.parse(source)
    model = ModuleModel(label=label, tree=tree, source=source)

    def _add_function(
        node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str, kind: Scope
    ) -> FunctionScope:
        fn = FunctionScope(
            qualname=qualname,
            scope=kind,
            complexity=_cyclomatic(node),
            scope_key=scope_key(label, qualname),
        )
        model.functions.append(fn)
        return fn

    def _visit_class(node: ast.ClassDef, prefix: str) -> None:
        qualname = f"{prefix}{node.name}"
        cls = ClassScope(
            qualname=qualname,
            bases=[_base_name(b) for b in node.bases],
            node=node,
            scope_key=scope_key(label, qualname),
        )
        model.classes.append(cls)
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = _add_function(child, f"{qualname}.{child.name}", Scope.METHOD)
                cls.methods.append(method)
            elif isinstance(child, ast.ClassDef):
                _visit_class(child, f"{qualname}.")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _add_function(node, node.name, Scope.FUNCTION)
        elif isinstance(node, ast.ClassDef):
            _visit_class(node, "")

    return model
