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

from coding_agent_playbook.grading.scope import Scope

#: AST node types that each contribute one decision point on their own.
_DECISION_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Assert,
    ast.match_case,
)


def scope_key(label: str, qualname: str | None) -> str:
    """Build a stable scope key: ``<label>::<qualname>`` or ``<label>`` (file).

    The key is deliberately qualname-based and line-independent (no lineno
    suffix) so a scope keeps the same key when its body moves up or down the
    file - that line-stability is what lets ``grade()`` match a candidate to its
    baseline after edits. The trade-off: sibling defs that share a qualname
    (a redefinition, ``@overload`` stubs, or ``if TYPE_CHECKING:`` conditional
    defs) collapse to the same key, and ``grade()``'s baseline index is
    last-wins for such rare collisions. This is intentional - a lineno suffix
    would fix the collision but break non-regression matching when code moves.
    """
    return label if qualname is None else f"{label}::{qualname}"


def _cyclomatic(node: ast.AST) -> int:
    """Cyclomatic complexity of one function/method body.

    ``1 + decision points``. Decision points are ``If``/``For``/``AsyncFor``/
    ``While``, each ``ExceptHandler``, ``IfExp``, ``assert``, and ``match``
    ``case`` guards; each ``BoolOp`` adds ``len(values) - 1``. A comprehension
    contributes **one per ``if`` filter** (``len(comp.ifs)``) - the generator
    loop itself adds nothing, so ``[x for x in xs]`` is ``+0``,
    ``[x for x in xs if a]`` is ``+1`` and ``[x for x in xs if a if b]`` is
    ``+2`` (matching radon's "comprehension ``if`` clauses"). A bare
    ``match_case`` with no guard contributes nothing; a guarded one adds one for
    the guard. The walk descends into ``lambda`` bodies (a lambda is not its own
    scope, so its decisions count toward the host callable) but **not** into
    nested function or class definitions, so each ``def``/``class`` is measured
    locally and WMC can sum the per-method values independently.
    """
    complexity = 1
    for child in _walk_local(node):
        if isinstance(child, ast.match_case):
            if child.guard is not None:
                complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += len(child.ifs)
        elif isinstance(child, _DECISION_NODES):
            complexity += 1
    return complexity


def _walk_local(node: ast.AST) -> list[ast.AST]:
    """Collect every descendant of ``node`` that counts toward *its own* CC.

    The walk starts from the function body and statements only - it deliberately
    excludes the callable's own ``decorator_list`` and its argument-default
    expressions, since decorators and defaults are not part of the function's
    control flow. It descends into ``lambda`` bodies (a lambda is not its own
    scope, so its decisions belong to the host callable) but stops at nested
    ``def``/``class`` definitions, which are separate scopes.
    """
    collected: list[ast.AST] = []
    stack: list[ast.AST] = list(_local_roots(node))
    while stack:
        current = stack.pop()
        collected.append(current)
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Do not descend into a nested scope's body (lambdas are not scopes).
            continue
        stack.extend(ast.iter_child_nodes(current))
    return collected


def _local_roots(node: ast.AST) -> list[ast.AST]:
    """Direct children of ``node`` that belong to its own body/control flow.

    For a ``def``/``async def`` this is the body plus any annotation/return
    expressions, but **not** the ``decorator_list`` or the ``arguments`` defaults
    (which are evaluated in the enclosing scope, not part of this callable's
    control flow). For any other node it is just its direct children.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return list(node.body)
    return list(ast.iter_child_nodes(node))


@dataclass
class FunctionScope:
    """A function or method, with its precomputed cyclomatic complexity and its AST node.

    ``node`` is retained (like :attr:`ClassScope.node`) so ``docstring_example``
    reads the def's docstring without re-parsing; it stays out of ``repr`` and
    equality, which compare the measured shape only.
    """

    qualname: str
    scope: Scope
    complexity: int
    scope_key: str
    node: ast.FunctionDef | ast.AsyncFunctionDef | None = field(
        default=None, repr=False, compare=False
    )


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
            node=node,
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
