"""The sample compiler: parsed ``[gate]``/``[rubric]``/``[verdict]``/``[aggregate]`` -> a per-trial structure.

This module turns the three new sample blocks into one
:class:`CompiledSample`: a :class:`~coding_agent_playbook.grading.rubric.Rubric`
carrying the two **named layer checks** (``id="gate"`` / ``id="rubric"``) plus a
*derived* verdict AST.

The defining design choice is that the verdict is **derived, not re-run**. The
per-trial rubric evaluates **gate once** and **rubric once** - they are its two
checks. The ``[verdict].trial`` expression (default ``"gate and rubric"``) is a
boolean function over the two layers' ``passed`` results, evaluated *after* the
rubric ran via :func:`~coding_agent_playbook.evals.compile._expr.eval_bool` over
``{"gate": …, "rubric": …}``. If the verdict were instead a third *check* that
re-composed gate/rubric, the judge (rubric) and the test suite / file predicates
(gate) would be invoked **twice** per trial; deriving it from the already-run
``CheckResult`` rows keeps each layer single-shot.

Each layer is compiled from its ``[<layer>.bind]`` table (via
:func:`~coding_agent_playbook.evals.compile._handles.build_handles`) and its ``expr``
(via :func:`~coding_agent_playbook.evals.compile._expr.compile_expr`), then wrapped in a
single-child :class:`~coding_agent_playbook.grading.compose.AllOf`
labeled with the layer id so the layer check's ``id`` is **always** ``"gate"`` /
``"rubric"`` (a bare single-name ``expr`` compiles to the handle check itself,
which carries the handle's id - the wrapper re-labels it without changing the
verdict). A layer with exactly one handle and no ``expr`` defaults the expr to
that handle's name (the common single-handle case); a layer with multiple handles
and no ``expr`` is an error - the author must compose them.

This compiler is what the sample pipeline runs:
:func:`coding_agent_playbook.evals.sample.compile_eval_sample` calls
:func:`compile_sample` for the validator (trial-compile) and the scoring bridge
(:mod:`coding_agent_playbook.evals.run.scoring`), and the runner reads
:attr:`CompiledSample.trials_needed` + :attr:`CompiledSample.aggregate` to drive the
multi-trial ``[aggregate]`` layer (the ``over`` selector flows through
:func:`over_boolean`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from coding_agent_playbook.evals.compile._expr import (
    And,
    Name,
    Node,
    Not,
    compile_expr,
    names,
    parse,
)
from coding_agent_playbook.evals.compile._handles import build_handles
from coding_agent_playbook.grading.compose import AllOf
from coding_agent_playbook.grading.rubric import Rubric

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.evals.checks.aggregate import AggregateCheck
    from coding_agent_playbook.grading.check import Check
    from coding_agent_playbook.grading.types import CheckResult, EvaluationReport

#: The default ``[verdict].trial`` expression: both layers must pass.
_DEFAULT_VERDICT = "gate and rubric"

#: The two layer ids a compiled sample may expose (verdict names are a subset).
_LAYER_IDS = ("gate", "rubric")

#: Tolerance for the weighted-verdict ``weights`` sum check (parity with the
#: rubric-group sum rule + ``[verdict].weights`` parser).
_WEIGHT_SUM_TOLERANCE = 1e-3


@dataclass(frozen=True)
class VerdictSpec:
    """The compiled ``[verdict]``: a boolean expr OR a weighted composite (C10).

    Mutually exclusive forms (mirrors :class:`~coding_agent_playbook.evals.sample.Verdict`):

    * ``mode == "boolean"`` — :attr:`ast` is the parsed ``[verdict].trial``
      expression and is folded by :func:`verdict_passed` over the layer
      :class:`~coding_agent_playbook.grading.types.CheckResult` results
      (skipped-neutral); :attr:`weights` / :attr:`fail` / :attr:`warn` are
      ``None``.
    * ``mode == "weighted"`` — :attr:`weights` is the validated layer-name to
      weight map (subset of present layers, sums to ``1.0`` ±1e-3), :attr:`fail`
      is the ``0-1`` composite cutoff (``passed = score >= fail``), :attr:`warn`
      is optional, and :attr:`ast` is unused (a placeholder for the dataclass).
    """

    mode: Literal["boolean", "weighted"]
    ast: Node
    weights: dict[str, float] | None = None
    fail: float | None = None
    warn: float | None = None


@dataclass(frozen=True)
class CompiledSample:
    """The per-trial evaluation structure for one sample (+ the aggregate layer).

    :attr:`per_trial` is the :class:`~coding_agent_playbook.grading.rubric.Rubric`
    carrying the present layer checks (``id="gate"`` and/or ``id="rubric"``, in
    that order); a single ``Rubric.evaluate`` runs each layer once.
    :attr:`verdict_spec` is the compiled :class:`VerdictSpec` - either the
    boolean ``[verdict].trial`` (folded by :func:`verdict_passed` over the two
    layers' ``passed`` results) or a weighted composite (folded by
    :func:`weighted_verdict` over the layers' 0-1 scores). :attr:`verdict_ast`
    is a convenience alias for ``verdict_spec.ast`` (the boolean-mode AST).
    :attr:`layers` is the frozenset of present layer ids (a subset of
    ``{"gate", "rubric"}``).

    :attr:`aggregate` is the compiled ``[aggregate]`` layer - one composed
    :class:`~coding_agent_playbook.grading.check.Check` over the
    :class:`~coding_agent_playbook.evals.checks.aggregate.AggregateCheck`
    handles - or ``None`` when the sample authored no ``[aggregate]`` block.
    :attr:`trials_needed` is the number of runner trials the aggregate layer needs
    (``max`` of every aggregate handle's ``k``), defaulting to **1** with no
    aggregate so the sample runs a single trial. :attr:`aggregate_overs` is the set
    of ``over`` axes the aggregate handles reduce (empty with no aggregate).
    """

    per_trial: Rubric
    verdict_spec: VerdictSpec
    layers: frozenset[str]
    aggregate: Check | None = None
    trials_needed: int = 1
    aggregate_overs: frozenset[str] = frozenset()

    @property
    def short_circuit_safe(self) -> bool:
        """Whether the cross-layer short-circuit can never change this sample's result.

        With ``fail_fast`` the per-trial scheduler stops grading costlier layers
        once a cheaper *required* layer failed. That only saves work — rather
        than changing an outcome — when the failure already decides everything
        downstream: (1) the verdict is a pure conjunction over every present
        layer (``gate and rubric``); under ``or``/``not``, a verdict naming only
        one of two layers, or a weighted verdict, a skipped (neutral) layer can
        flip it — e.g. ``trial = "rubric"`` with a failing gate passed. And (2) no
        ``[aggregate]`` reduces a layer the short-circuit could skip (one costlier
        than the cheapest layer). :func:`coding_agent_playbook.evals.run.scoring.score`
        turns ``fail_fast`` off when this is ``False``.
        """
        return self._verdict_is_full_conjunction() and not self._aggregate_reads_skippable_layer()

    def _verdict_is_full_conjunction(self) -> bool:
        if self.verdict_spec.mode != "boolean":
            return False
        return _conjoined_names(self.verdict_spec.ast) == set(self.layers)

    def _aggregate_reads_skippable_layer(self) -> bool:
        layers = self.per_trial.checks
        cheapest = min(layer.cost for layer in layers)
        return any(layer.id in self.aggregate_overs and layer.cost > cheapest for layer in layers)

    @property
    def verdict_ast(self) -> Node:
        """The boolean-mode verdict AST (convenience alias for ``verdict_spec.ast``)."""
        return self.verdict_spec.ast


def _conjoined_names(node: Node) -> set[str] | None:
    """The names of a pure conjunction (``a`` or ``a and b``), else ``None``."""
    if isinstance(node, Name):
        return {node.value}
    if not isinstance(node, And):
        return None
    leaves = [child for child in node.children if isinstance(child, Name)]
    if len(leaves) != len(node.children):
        return None
    return {leaf.value for leaf in leaves}


def _compile_layer(
    bind_table: Mapping[str, Mapping[str, Any]] | None,
    expr: str | None,
    *,
    layer: str,
) -> Check | None:
    """Compile one layer (``gate``/``rubric``) into a single composed :class:`Check`.

    Returns ``None`` when ``bind_table`` is absent or empty - the layer is not
    present. Otherwise builds the handle map
    (:func:`~coding_agent_playbook.evals.compile._handles.build_handles`) and compiles
    ``expr`` over it (:func:`~coding_agent_playbook.evals.compile._expr.compile_expr`).
    When ``expr`` is absent the layer defaults to its sole handle's name iff there
    is exactly one handle; with multiple handles and no ``expr`` it raises
    :exc:`ValueError` (the author must compose them).

    The compiled expression is wrapped in a single-child
    :class:`~coding_agent_playbook.grading.compose.AllOf` labeled with
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


def compile_sample(
    *,
    gate_bind: Mapping[str, Mapping[str, Any]] | None = None,
    gate_expr: str | None = None,
    rubric_bind: Mapping[str, Mapping[str, Any]] | None = None,
    rubric_expr: str | None = None,
    verdict_trial: str | None = None,
    verdict_weights: Mapping[str, float] | None = None,
    verdict_fail: float | None = None,
    verdict_warn: float | None = None,
    aggregate_bind: Mapping[str, Mapping[str, Any]] | None = None,
    aggregate_expr: str | None = None,
    name: str = "sample",
) -> CompiledSample:
    """Compile the parsed sample blocks into a :class:`CompiledSample`.

    Builds the ``gate`` and ``rubric`` layer checks (each :func:`_compile_layer`,
    ``None`` when its block is absent), assembles the present ones - in
    ``gate, rubric`` order - into the per-trial
    :class:`~coding_agent_playbook.grading.rubric.Rubric` named ``name``, and
    compiles the verdict spec (boolean ``verdict_trial`` OR weighted
    ``verdict_weights`` / ``verdict_fail`` / ``verdict_warn`` - mutually
    exclusive). Raises :exc:`ValueError` when **no** layer is present, when the
    boolean ``verdict_trial`` references a layer that is absent (e.g. the default
    ``"gate and rubric"`` on a gate-only sample), or when the weighted
    ``verdict_weights`` keys are not a subset of the present layers / fail to sum
    to ``1.0`` / no ``verdict_fail`` cutoff is provided.

    Passing **both** ``verdict_trial`` (or its default) and ``verdict_weights``
    is a :exc:`ValueError` (the two modes are mutually exclusive); passing
    neither defaults to the boolean ``"gate and rubric"``.

    The ``[aggregate]`` layer is compiled the same way as gate/rubric - its bind
    table builds
    :class:`~coding_agent_playbook.evals.checks.aggregate.AggregateCheck`
    handles (via the ``metric``-alone fallback in
    :func:`~coding_agent_playbook.evals.compile._handles._build_one`), and its ``expr``
    composes them - into :attr:`CompiledSample.aggregate` (``None`` when absent).
    :attr:`CompiledSample.trials_needed` is the ``max`` ``k`` over those handles,
    defaulting to **1** with no aggregate so the sample runs a single trial.
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
        raise ValueError("a sample must have at least one of [gate] / [rubric]")

    verdict_spec = _compile_verdict(
        verdict_trial=verdict_trial,
        verdict_weights=verdict_weights,
        verdict_fail=verdict_fail,
        verdict_warn=verdict_warn,
        present=present,
    )

    aggregate, trials_needed, aggregate_overs = _compile_aggregate(aggregate_bind, aggregate_expr)

    per_trial = Rubric(checks, name=name)
    return CompiledSample(
        per_trial=per_trial,
        verdict_spec=verdict_spec,
        layers=present,
        aggregate=aggregate,
        trials_needed=trials_needed,
        aggregate_overs=aggregate_overs,
    )


def _compile_verdict(
    *,
    verdict_trial: str | None,
    verdict_weights: Mapping[str, float] | None,
    verdict_fail: float | None,
    verdict_warn: float | None,
    present: frozenset[str],
) -> VerdictSpec:
    """Compile the verdict knobs into a :class:`VerdictSpec` (validated).

    Mutual exclusion: ``verdict_trial`` (or its absence -> default) and
    ``verdict_weights`` are the two modes; passing both is a :exc:`ValueError`.
    The weighted form additionally validates: ``verdict_weights`` is non-empty,
    its keys ⊆ ``present`` layers, the values sum to ``1.0`` (±1e-3), and
    ``verdict_fail`` is provided.
    """
    has_trial = verdict_trial is not None
    has_weights = verdict_weights is not None
    if has_trial and has_weights:
        raise ValueError("[verdict] cannot set both 'trial' and 'weights'")

    if has_weights:
        assert verdict_weights is not None
        if not verdict_weights:
            raise ValueError("[verdict].weights must be non-empty")
        weights = {str(k): float(v) for k, v in verdict_weights.items()}
        total = sum(weights.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"[verdict].weights must sum to 1.0 (got {total!r}; "
                f"tolerance ±{_WEIGHT_SUM_TOLERANCE})"
            )
        unknown = set(weights) - present
        if unknown:
            raise ValueError(
                f"[verdict].weights references unknown layer(s) "
                f"{sorted(unknown)!r}; present: {sorted(present)}"
            )
        if verdict_fail is None:
            raise ValueError("[verdict] weighted form requires 'fail'")
        # Parse() needs *some* AST so the dataclass field is non-None; the
        # weighted-mode resolver never reads it.
        return VerdictSpec(
            mode="weighted",
            ast=parse(_DEFAULT_VERDICT),
            weights=weights,
            fail=float(verdict_fail),
            warn=float(verdict_warn) if verdict_warn is not None else None,
        )

    # Boolean form (default / explicit `trial = …`).
    trial = verdict_trial if verdict_trial is not None else _DEFAULT_VERDICT
    verdict_ast = parse(trial)
    referenced = names(trial)
    unknown_idents = referenced - present
    if unknown_idents:
        missing = sorted(unknown_idents)[0]
        raise ValueError(
            f"[verdict].trial references {missing!r} but there is no "
            f"[{missing}] block (present layers: {sorted(present)})"
        )
    return VerdictSpec(mode="boolean", ast=verdict_ast)


def _compile_aggregate(
    bind_table: Mapping[str, Mapping[str, Any]] | None,
    expr: str | None,
) -> tuple[Check | None, int, frozenset[str]]:
    """Compile ``[aggregate]`` into ``(check | None, trials_needed, overs)``.

    Returns ``(None, 1, frozenset())`` when ``bind_table`` is absent/empty (no
    aggregate ⇒ the runner runs a single trial). Otherwise builds the
    :class:`~coding_agent_playbook.evals.checks.aggregate.AggregateCheck`
    handle map (the ``metric``-alone fallback in
    :func:`~coding_agent_playbook.evals.compile._handles._build_one`), compiles ``expr``
    over it (defaulting to the sole handle's name for a single-handle layer; a
    multi-handle layer with no ``expr`` is a :exc:`ValueError`), and reads every
    reachable :class:`AggregateCheck`: ``trials_needed`` is the ``max`` of their
    ``k`` and ``overs`` the set of their ``over`` axes.
    """
    if not bind_table:
        return None, 1, frozenset()
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
    leaves = _aggregate_leaves(handles.values())
    trials_needed = max((leaf.k for leaf in leaves), default=1)
    return compiled, trials_needed, frozenset(leaf.over for leaf in leaves)


def _aggregate_leaves(checks: Iterable[Check]) -> list[AggregateCheck]:
    """Every :class:`AggregateCheck` reachable under ``checks``.

    Descends the boolean composers (``AllOf``/``AnyOf``/``Not`` via ``children``),
    so a composed aggregate expression (e.g. ``pass_at_k(k=5) and pass_pow_k(k=3)``)
    yields both leaves.
    """
    from coding_agent_playbook.evals.checks.aggregate import AggregateCheck
    from coding_agent_playbook.grading.compose import AllOf, AnyOf, Not

    out: list[AggregateCheck] = []

    def _walk(check: Check) -> None:
        if isinstance(check, AggregateCheck):
            out.append(check)
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
    an unavailable child in :class:`~coding_agent_playbook.grading.compose.AllOf`
    / :class:`~coding_agent_playbook.grading.compose.AnyOf` (only *run*
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

    A :class:`~coding_agent_playbook.evals.compile._expr.Name` resolves to its tri-state in
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


def weighted_verdict(
    report: EvaluationReport,
    spec: VerdictSpec,
) -> tuple[float | None, bool]:
    """Derive the weighted-composite verdict (score, passed) from ``report``.

    Walks ``report.checks`` for each layer in ``spec.weights``, dropping any
    that the per-trial rubric recorded as ``status="skipped"`` (or are missing
    from the report entirely - should not happen since the compiler validated
    layer presence). The remaining layers' weights are *renormalized* to sum to
    ``1.0``, each layer's ``0-1`` score is derived via :func:`_layer_score`, and
    the composite is the weighted sum ``Σ(w_i · score_i)``. ``passed`` is
    ``composite >= spec.fail`` (strict-below the cutoff fails - parity with the
    higher-is-better convention everywhere else).

    If **every** referenced layer is skipped the composite cannot be computed:
    returns ``(None, True)`` (vacuously passing, mirroring the skipped-neutral
    semantics of :func:`verdict_passed`).
    """
    if spec.mode != "weighted":
        raise ValueError(f"weighted_verdict called on a {spec.mode!r}-mode VerdictSpec")
    assert spec.weights is not None  # narrowed by the mode check above.
    assert spec.fail is not None

    layer_results: dict[str, CheckResult] = {c.check_id: c for c in report.checks}
    contributions: list[tuple[float, float]] = []  # (weight, score)
    for layer_id, weight in spec.weights.items():
        result = layer_results.get(layer_id)
        if result is None or result.status != "run":
            continue  # skipped or missing -> renormalize over the rest.
        score = _layer_score(result)
        if score is None:
            # The layer ran but no leaf carried a score — e.g. a metric threshold
            # graded over zero scopes. (A judge-less rubric layer no longer gets
            # here: its composer is skipped and filtered above.) Treat as
            # effectively skipped: exclude + renormalize.
            continue
        contributions.append((weight, score))

    if not contributions:
        return (None, True)  # all referenced layers skipped -> vacuous pass.

    total_weight = sum(w for w, _ in contributions)
    if total_weight <= 0:
        return (None, True)  # defensive: no positive weight contributes.
    composite = sum(w * s for w, s in contributions) / total_weight
    passed = composite >= spec.fail
    return (composite, passed)


def _layer_score(layer_result: CheckResult) -> float | None:
    """A single ``0-1`` score for one verdict layer's :class:`CheckResult`.

    Two paths, in order:

    1. ``layer_result.score`` itself when it is a finite ``0-1`` float and the
       result is a *true* leaf (subresults are scope-details, not nested
       CheckResults) - the rubric layer's path when its inner ThresholdCheck is
       the layer's "score" leaf already. Boolean composers like :class:`AllOf`
       set ``score=1.0/0.0`` from ``passed``; those don't qualify and reduce to
       the mean-of-leaves path below.
    2. Mean of leaf-:class:`CheckResult` scores under ``layer_result.subresults``,
       recursing through nested composing checks. A "leaf" is a CheckResult whose
       ``subresults`` are all :class:`~coding_agent_playbook.grading.types.ScopeDetail`
       rows (or empty). Skipped leaves contribute nothing.

    Returns ``None`` when no leaf contributed a score - the layer ran (as a
    composer) but every leaf that ran was unscored and the scored ones were
    skipped. (A layer none of whose leaves can run is itself skipped and never
    reaches here.) :func:`weighted_verdict` treats ``None`` as
    effectively-skipped and renormalizes over the rest.
    """
    own_score = layer_result.score
    if own_score is not None and 0.0 <= own_score <= 1.0 and not _is_boolean_score(layer_result):
        return own_score
    return _mean_leaf_scores(layer_result)


def _is_boolean_score(result: CheckResult) -> bool:
    """Whether ``result.score`` is a pure boolean-collapsed ``1.0``/``0.0``.

    The boolean composers (:class:`AllOf` / :class:`AnyOf` / :class:`Not`) set
    ``score = 1.0 if passed else 0.0`` from their verdict - the score does not
    carry partial-credit information. A leaf metric check (``ThresholdCheck`` /
    ``NonRegressionCheck``) sets ``score`` to the mean per-scope normalized
    score, which is rarely *exactly* ``0.0``/``1.0`` but may legitimately be -
    so we also peek at the structure: a composer has nested
    :class:`CheckResult` subresults, a leaf has :class:`ScopeDetail` (or empty).
    """
    from coding_agent_playbook.grading.types import CheckResult as _CR

    if not result.subresults:
        return False
    return all(isinstance(sub, _CR) for sub in result.subresults)


def _mean_leaf_scores(layer_result: CheckResult) -> float | None:
    """Equal-weight mean of leaf-CheckResult scores recursed under ``layer_result``.

    A "leaf" is a CheckResult whose subresults are all :class:`ScopeDetail` rows
    (or empty) - the deterministic file/threshold checks and judge checks. A
    composer (``AllOf`` / ``AnyOf`` / ``Not`` / nested ``Rubric``) is descended
    via its ``CheckResult`` subresults. Skipped leaves are dropped. Returns
    ``None`` when no leaf contributed - the caller (:func:`_layer_score` /
    :func:`weighted_verdict`) treats that as effectively-skipped.
    """
    from coding_agent_playbook.grading.types import CheckResult as _CR

    scores: list[float] = []

    def _walk(result: CheckResult) -> None:
        if result.status != "run":
            return
        nested = [sub for sub in result.subresults if isinstance(sub, _CR)]
        if nested:
            # A composing check (boolean composer or a nested rubric); descend.
            for child in nested:
                _walk(child)
            return
        # A leaf: collect its own score if any.
        if result.score is not None:
            scores.append(result.score)

    _walk(layer_result)
    if not scores:
        return None
    return sum(scores) / len(scores)


def over_boolean(over: str, report: EvaluationReport, verdict: bool) -> bool | None:
    """Select the boolean an aggregate ``over`` axis reduces, for one trial.

    ``over == "verdict"`` returns the passed-in ``verdict`` (already derived via
    :func:`verdict_passed`); ``over`` in ``{"gate", "rubric"}`` returns that
    layer's ``CheckResult.passed`` from ``report.checks``, or ``None`` when the
    layer was skipped (neutral — it does not vote). Raises
    :exc:`ValueError` when ``over`` is neither ``"verdict"`` nor a present layer
    id (an unknown axis, or a layer the sample does not have). Used by the
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
            return check.passed if check.status == "run" else None
    raise ValueError(f"'over' selector {over!r} has no {over!r} check in the report")


__all__ = [
    "CompiledSample",
    "VerdictSpec",
    "compile_sample",
    "over_boolean",
    "verdict_passed",
    "weighted_verdict",
]
