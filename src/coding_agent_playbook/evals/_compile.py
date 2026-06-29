"""The task compiler (Track C6): parsed ``[gate]``/``[rubric]``/``[verdict]`` -> a per-trial structure.

This module turns the three new task blocks into one
:class:`CompiledTask`: a :class:`~coding_agent_playbook.evaluators.rubric.Rubric`
carrying the two **named layer checks** (``id="gate"`` / ``id="rubric"``) plus a
*derived* verdict AST.

The defining design choice is that the verdict is **derived, not re-run**. The
per-trial rubric evaluates **gate once** and **rubric once** - they are its two
checks. The ``[verdict].trial`` expression (default ``"gate and rubric"``) is a
boolean function over the two layers' ``passed`` results, evaluated *after* the
rubric ran via :func:`~coding_agent_playbook.evals._expr.eval_bool` over
``{"gate": …, "rubric": …}``. If the verdict were instead a third *check* that
re-composed gate/rubric, the judge (rubric) and the test suite / file predicates
(gate) would be invoked **twice** per trial; deriving it from the already-run
``CheckResult`` rows keeps each layer single-shot.

Each layer is compiled from its ``[<layer>.bind]`` table (via
:func:`~coding_agent_playbook.evals._handles.build_handles`) and its ``expr``
(via :func:`~coding_agent_playbook.evals._expr.compile_expr`), then wrapped in a
single-child :class:`~coding_agent_playbook.evaluators.checks.compose.AllOf`
labeled with the layer id so the layer check's ``id`` is **always** ``"gate"`` /
``"rubric"`` (a bare single-name ``expr`` compiles to the handle check itself,
which carries the handle's id - the wrapper re-labels it without changing the
verdict). A layer with exactly one handle and no ``expr`` defaults the expr to
that handle's name (the common single-handle case); a layer with multiple handles
and no ``expr`` is an error - the author must compose them.

It is purely additive (Track C6): nothing in the task pipeline consumes it yet
(C7 swaps the parser; C8 wires the aggregate ``over`` selector through
:func:`over_boolean`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals._expr import (
    And,
    Name,
    Node,
    Not,
    compile_expr,
    names,
    parse,
)
from coding_agent_playbook.evals._handles import build_handles
from coding_agent_playbook.evaluators.checks.compose import AllOf
from coding_agent_playbook.evaluators.rubric import Rubric

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.types import EvaluationReport

#: The default ``[verdict].trial`` expression: both layers must pass.
_DEFAULT_VERDICT = "gate and rubric"

#: The two layer ids a compiled task may expose (verdict names are a subset).
_LAYER_IDS = ("gate", "rubric")


@dataclass(frozen=True)
class CompiledTask:
    """The per-trial evaluation structure for one task (+ the C8 aggregate layer).

    :attr:`per_trial` is the :class:`~coding_agent_playbook.evaluators.rubric.Rubric`
    carrying the present layer checks (``id="gate"`` and/or ``id="rubric"``, in
    that order); a single ``Rubric.evaluate`` runs each layer once.
    :attr:`verdict_ast` is the parsed ``[verdict].trial`` expression, evaluated
    by :func:`verdict_passed` over the two layers' ``passed`` results into the
    single trial verdict. :attr:`layers` is the frozenset of present layer ids
    (a subset of ``{"gate", "rubric"}``).

    :attr:`aggregate` (C8) is the compiled ``[aggregate]`` layer - one composed
    :class:`~coding_agent_playbook.evaluators.check.Check` over the
    :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    handles - or ``None`` when the task authored no ``[aggregate]`` block.
    :attr:`trials_needed` is the number of runner trials the aggregate layer needs
    (``max`` of every aggregate handle's ``k``), defaulting to **1** with no
    aggregate so the single-trial path is byte-identical to C7.
    """

    per_trial: Rubric
    verdict_ast: Node
    layers: frozenset[str]
    aggregate: Check | None = None
    trials_needed: int = 1


def _compile_layer(
    bind_table: Mapping[str, Mapping[str, Any]] | None,
    expr: str | None,
    *,
    layer: str,
) -> Check | None:
    """Compile one layer (``gate``/``rubric``) into a single composed :class:`Check`.

    Returns ``None`` when ``bind_table`` is absent or empty - the layer is not
    present. Otherwise builds the handle map
    (:func:`~coding_agent_playbook.evals._handles.build_handles`) and compiles
    ``expr`` over it (:func:`~coding_agent_playbook.evals._expr.compile_expr`).
    When ``expr`` is absent the layer defaults to its sole handle's name iff there
    is exactly one handle; with multiple handles and no ``expr`` it raises
    :exc:`ValueError` (the author must compose them).

    The compiled expression is wrapped in a single-child
    :class:`~coding_agent_playbook.evaluators.checks.compose.AllOf` labeled with
    ``layer`` so the returned check's ``id`` is **always** the layer name
    (``"gate"``/``"rubric"``) - a bare single-name ``expr`` would otherwise
    compile to the handle check itself, carrying the handle's id. ``AllOf`` over
    one child passes iff that child passes, so this re-labels without changing the
    verdict and the inner check still runs exactly once.
    """
    if not bind_table:
        return None
    handles = build_handles(bind_table, layer=layer)
    resolved_expr = expr
    if resolved_expr is None:
        if len(handles) == 1:
            resolved_expr = next(iter(handles))
        else:
            raise ValueError(
                f"[{layer}] has {len(handles)} handles and no expr; "
                "the author must compose them with an explicit expr"
            )
    compiled = compile_expr(resolved_expr, handles, id=layer)
    return AllOf(compiled, id=layer)


def compile_task(
    *,
    gate_bind: Mapping[str, Mapping[str, Any]] | None = None,
    gate_expr: str | None = None,
    rubric_bind: Mapping[str, Mapping[str, Any]] | None = None,
    rubric_expr: str | None = None,
    verdict_trial: str = _DEFAULT_VERDICT,
    aggregate_bind: Mapping[str, Mapping[str, Any]] | None = None,
    aggregate_expr: str | None = None,
    name: str = "task",
) -> CompiledTask:
    """Compile the parsed task blocks into a :class:`CompiledTask`.

    Builds the ``gate`` and ``rubric`` layer checks (each :func:`_compile_layer`,
    ``None`` when its block is absent), assembles the present ones - in
    ``gate, rubric`` order - into the per-trial
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric` named ``name``, and
    parses ``verdict_trial`` into the verdict AST. Raises :exc:`ValueError` when
    **no** layer is present, or when ``verdict_trial`` references a layer that is
    absent (e.g. the default ``"gate and rubric"`` on a gate-only task).

    The ``[aggregate]`` layer (C8) is compiled the same way as gate/rubric - its
    bind table builds
    :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    handles (via the ``metric``-alone fallback in
    :func:`~coding_agent_playbook.evals._handles._build_one`), and its ``expr``
    composes them - into :attr:`CompiledTask.aggregate` (``None`` when absent).
    :attr:`CompiledTask.trials_needed` is the ``max`` ``k`` over those handles,
    defaulting to **1** with no aggregate so the single-trial path matches C7.
    """
    gate_check = _compile_layer(gate_bind, gate_expr, layer="gate")
    rubric_check = _compile_layer(rubric_bind, rubric_expr, layer="rubric")

    layered: list[tuple[str, Check | None]] = [
        ("gate", gate_check),
        ("rubric", rubric_check),
    ]
    checks: list[Check] = [check for _, check in layered if check is not None]
    present = frozenset(layer for layer, check in layered if check is not None)
    if not checks:
        raise ValueError("a task must have at least one of [gate] / [rubric]")

    verdict_ast = parse(verdict_trial)
    referenced = names(verdict_trial)
    unknown = referenced - present
    if unknown:
        missing = sorted(unknown)[0]
        raise ValueError(
            f"[verdict].trial references {missing!r} but there is no "
            f"[{missing}] block (present layers: {sorted(present)})"
        )

    aggregate, trials_needed = _compile_aggregate(aggregate_bind, aggregate_expr)

    per_trial = Rubric(checks, name=name)
    return CompiledTask(
        per_trial=per_trial,
        verdict_ast=verdict_ast,
        layers=present,
        aggregate=aggregate,
        trials_needed=trials_needed,
    )


def _compile_aggregate(
    bind_table: Mapping[str, Mapping[str, Any]] | None,
    expr: str | None,
) -> tuple[Check | None, int]:
    """Compile the ``[aggregate]`` layer into ``(check | None, trials_needed)``.

    Returns ``(None, 1)`` when ``bind_table`` is absent/empty (no aggregate ⇒ the
    runner runs a single trial, matching C7). Otherwise builds the
    :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    handle map (the ``metric``-alone fallback in
    :func:`~coding_agent_playbook.evals._handles._build_one`), compiles ``expr``
    over it (defaulting to the sole handle's name for a single-handle layer; a
    multi-handle layer with no ``expr`` is a :exc:`ValueError`), and computes
    ``trials_needed`` as the ``max`` ``k`` over every
    :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    reachable in the compiled tree.
    """
    if not bind_table:
        return None, 1
    handles = build_handles(bind_table, layer="aggregate")
    resolved_expr = expr
    if resolved_expr is None:
        if len(handles) == 1:
            resolved_expr = next(iter(handles))
        else:
            raise ValueError(
                f"[aggregate] has {len(handles)} handles and no expr; "
                "the author must compose them with an explicit expr"
            )
    compiled = compile_expr(resolved_expr, handles, id="aggregate")
    trials_needed = max((k for k in _aggregate_ks(handles.values())), default=1)
    return compiled, trials_needed


def _aggregate_ks(checks: Iterable[Check]) -> list[int]:
    """Every :class:`AggregateCheck`'s ``k`` reachable under ``checks``.

    Descends the boolean composers (``AllOf``/``AnyOf``/``Not`` via ``children``)
    and reads ``.k`` off each
    :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    leaf, so ``trials_needed`` is the ``max`` over a possibly-composed aggregate
    expression (e.g. ``pass_at_k(k=5) and pass_pow_k(k=3)`` ⇒ ``[5, 3]``).
    """
    from coding_agent_playbook.evaluators.checks.aggregate import AggregateCheck
    from coding_agent_playbook.evaluators.checks.compose import AllOf, AnyOf, Not

    out: list[int] = []

    def _walk(check: Check) -> None:
        if isinstance(check, AggregateCheck):
            out.append(check.k)
            return
        if isinstance(check, (AllOf, AnyOf, Not)):
            for child in check.children:
                _walk(child)

    for check in checks:
        _walk(check)
    return out


def verdict_passed(report: EvaluationReport, verdict_ast: Node) -> bool:
    """Derive the trial verdict from an evaluated report's layer results.

    Builds a ``check_id -> tri-state`` environment from ``report.checks`` (``True``/
    ``False`` for a layer that **ran**, ``None`` for a layer that was **skipped** —
    e.g. the rubric layer with no judge configured) and folds ``verdict_ast`` over
    it with **skipped-neutral** semantics: a skipped layer is neutral, exactly like
    an unavailable child in :class:`~coding_agent_playbook.evaluators.checks.compose.AllOf`
    / :class:`~coding_agent_playbook.evaluators.checks.compose.AnyOf` (only *run*
    layers vote). So ``gate and rubric`` with ``{gate=True, rubric=skipped}`` is
    ``True`` (the gate-only deterministic path), ``gate or rubric`` with
    ``{gate=False, rubric=skipped}`` is ``False``, and an all-skipped expression is
    vacuously ``True``.

    The two layers (``gate``/``rubric``) ran once inside ``report``; this never
    re-runs them, so the judge / test suite is not double-invoked.
    """
    env: dict[str, bool | None] = {}
    for check in report.checks:
        env[check.check_id] = check.passed if check.status == "run" else None
    return _eval_neutral(verdict_ast, env) is not False


def _eval_neutral(node: Node, env: Mapping[str, bool | None]) -> bool | None:
    """Tri-state fold of ``node`` over ``env``: ``True``/``False``/``None`` (neutral).

    A :class:`~coding_agent_playbook.evals._expr.Name` resolves to its tri-state in
    ``env`` (an absent name is neutral ``None``). ``And``/``Or`` drop neutral
    children and vote over the rest — an all-neutral ``And`` is ``None`` (vacuously
    fine), an all-neutral ``Or`` is ``None`` (nothing passed yet). ``Not`` over a
    neutral child stays neutral. :func:`verdict_passed` collapses a top-level
    neutral to ``True`` (a bare-AND / all-skipped trial passes).
    """
    if isinstance(node, Name):
        return env.get(node.value)
    if isinstance(node, Not):
        child = _eval_neutral(node.child, env)
        return None if child is None else not child
    children = [_eval_neutral(c, env) for c in node.children]
    voting = [c for c in children if c is not None]
    if not voting:
        return None
    if isinstance(node, And):
        return all(voting)
    # Or
    return any(voting)


def over_boolean(over: str, report: EvaluationReport, verdict: bool) -> bool:
    """Select the boolean an aggregate ``over`` axis reduces, for one trial.

    ``over == "verdict"`` returns the passed-in ``verdict`` (already derived via
    :func:`verdict_passed`); ``over`` in ``{"gate", "rubric"}`` returns that
    layer's ``CheckResult.passed`` from ``report.checks``. Raises
    :exc:`ValueError` when ``over`` is neither ``"verdict"`` nor a present layer
    id (an unknown axis, or a layer the task does not have). Used by C8's
    aggregate ``over`` selector.
    """
    if over == "verdict":
        return verdict
    if over not in _LAYER_IDS:
        raise ValueError(
            f"unknown 'over' selector {over!r}; expected 'verdict', 'gate', or 'rubric'"
        )
    for check in report.checks:
        if check.check_id == over:
            return check.passed
    raise ValueError(f"'over' selector {over!r} has no {over!r} check in the report")


__all__ = [
    "CompiledTask",
    "compile_task",
    "over_boolean",
    "verdict_passed",
]
