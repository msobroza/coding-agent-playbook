"""CBO~ - coupling between objects, approximate (SPEC prM §B/§I).

Counts the distinct external *type-like* names a class references: base classes,
parameter/return annotations, and bare-name constructor calls (``Foo()``). This
**undercounts under duck typing** (it can only see names that appear as types or
constructors) and is rendered as approximate. Builtins and the class's own name
are excluded.
"""

from __future__ import annotations

import ast
import builtins as _py_builtins
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
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

_BUILTIN_NAMES = frozenset(dir(_py_builtins))
_NAME = "cbo"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: one CBO~ (distinct external types) per class scope.

    Both the Evaluator and the Metric call this; the per-class coupled-type set is
    resolved by the module-level :func:`_coupled_types` helper, so the two layers
    stay in lockstep.
    """
    if ctx.module is None:
        return []
    own_names = {cls.qualname.rsplit(".", 1)[-1] for cls in ctx.module.classes}
    return [
        Measurement(
            evaluator=_NAME,
            scope_key=cls.scope_key,
            value=float(len(_coupled_types(cls, own_names))),
        )
        for cls in ctx.module.classes
    ]


@register_evaluator
class CouplingBetweenObjects(Evaluator):
    """CBO~ - distinct external types referenced by a class (approximate)."""

    name = _NAME
    scope = Scope.CLASS
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    requires = None
    default_absolute = AbsoluteThreshold(warn=14)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)


@register_metric
class CouplingBetweenObjectsMetric(Metric):
    """``cbo`` as a :class:`Metric` (shares :func:`_measure`)."""

    name = _NAME
    scope = Scope.CLASS
    higher_is_worse = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)


def _coupled_types(cls: ClassScope, own_names: set[str]) -> set[str]:
    names: set[str] = set()
    short_name = cls.qualname.rsplit(".", 1)[-1]

    for base in cls.node.bases:
        names |= _annotation_names(base)

    for sub in ast.walk(cls.node):
        # Constructor-style calls: ``Foo()`` / ``pkg.Foo()``.
        if isinstance(sub, ast.Call):
            names |= _callee_type_name(sub.func)
        # Annotations on args / returns / assignments.
        elif isinstance(sub, ast.arg) and sub.annotation is not None:
            names |= _annotation_names(sub.annotation)
        elif isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef) and sub.returns is not None:
            names |= _annotation_names(sub.returns)
        elif isinstance(sub, ast.AnnAssign):
            names |= _annotation_names(sub.annotation)

    names.discard(short_name)
    names.discard("self")
    return {n for n in names if n not in own_names and n not in _BUILTIN_NAMES}


def _callee_type_name(func: ast.expr) -> set[str]:
    """Type name for a constructor-style call target, else empty.

    Only counts calls whose callee is a *type-like* identifier: a bare ``Name``
    whose first character is uppercase (a class by convention), or the trailing
    attribute of a dotted ``pkg.Class`` reference.
    """
    if isinstance(func, ast.Name):
        return {func.id} if func.id[:1].isupper() else set()
    if isinstance(func, ast.Attribute):
        return {func.attr} if func.attr[:1].isupper() else set()
    return set()


def _annotation_names(node: ast.expr) -> set[str]:
    """Collect type-like names from an annotation/base expression.

    A dotted reference (``pkg.Class``) contributes only its trailing segment
    (the type), never the package qualifier, so ``framework.Base`` counts as one
    coupled type. Subscripts (``list[Foo]``) still surface their arguments.
    """
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Attribute):
        # Record the trailing type only; do not descend into the qualifier.
        names.add(node.attr)
    elif isinstance(node, ast.Subscript):
        names |= _annotation_names(node.value)
        names |= _annotation_names(node.slice)
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            names |= _annotation_names(elt)
    return names
