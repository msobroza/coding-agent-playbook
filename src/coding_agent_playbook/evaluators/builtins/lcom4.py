"""LCOM4 - connected components of a class's method graph (SPEC prM §B).

Two methods are linked when they share access to a ``self.<attr>`` instance
attribute, or when one calls the other via ``self.<method>()``. LCOM4 is the
number of connected components: ``1`` for a cohesive class, ``>1`` when the
class bundles unrelated responsibilities.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.parse import ClassScope
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "lcom4"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: one LCOM4 (connected-component count) per class scope.

    Delegates the graph work to the module-level :func:`_lcom4` helper.
    """
    if ctx.module is None:
        return []
    return [
        Measurement(
            evaluator=_NAME,
            scope_key=cls.scope_key,
            value=float(_lcom4(cls)),
        )
        for cls in ctx.module.classes
    ]


@register_metric
class LackOfCohesion4Metric(Metric):
    """``lcom4`` as a :class:`Metric` (shares :func:`_measure`)."""

    name = _NAME
    scope = Scope.CLASS
    higher_is_worse = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)


def _method_nodes(cls: ClassScope) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        child.name: child
        for child in cls.node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _self_attrs_and_calls(node: ast.AST) -> tuple[set[str], set[str]]:
    """Return (``self.x`` attribute names, ``self.m`` method-call names)."""
    attrs: set[str] = set()
    calls: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            target = sub.func
            if isinstance(target.value, ast.Name) and target.value.id == "self":
                calls.add(target.attr)
        if (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "self"
        ):
            attrs.add(sub.attr)
    return attrs, calls


def _lcom4(cls: ClassScope) -> int:
    methods = _method_nodes(cls)
    names = list(methods)
    if not names:
        return 0

    attrs: dict[str, set[str]] = {}
    calls: dict[str, set[str]] = {}
    for name, fn in methods.items():
        attr_set, call_set = _self_attrs_and_calls(fn)
        # A method calling itself does not couple it to anything else.
        call_set.discard(name)
        attrs[name] = attr_set
        calls[name] = call_set

    parent = {name: name for name in names}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    method_set = set(names)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if attrs[a] & attrs[b]:
                union(a, b)
        # method-call edges (only to sibling methods of this class)
        for callee in calls[a] & method_set:
            union(a, callee)

    return len({find(name) for name in names})
