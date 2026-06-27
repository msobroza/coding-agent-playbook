"""LCOM4 - connected components of a class's method graph (SPEC prM §B).

Two methods are linked when they share access to a ``self.<attr>`` instance
attribute, or when one calls the other via ``self.<method>()``. LCOM4 is the
number of connected components: ``1`` for a cohesive class, ``>1`` when the
class bundles unrelated responsibilities.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.parse import ClassScope
    from coding_agent_playbook.evaluators.types import EvalContext


@register_evaluator
class LackOfCohesion4(Evaluator):
    """LCOM4 cohesion metric (number of connected method components)."""

    name = "lcom4"
    scope = Scope.CLASS
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    requires = None
    default_absolute = AbsoluteThreshold(warn=2)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        if ctx.module is None:
            return []
        return [
            Measurement(
                evaluator=self.name,
                scope_key=cls.scope_key,
                value=float(_lcom4(cls)),
            )
            for cls in ctx.module.classes
        ]


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
