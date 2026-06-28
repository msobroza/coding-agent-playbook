"""The handle builder (Track C5): a ``[<layer>.bind]`` table -> ``name -> Check``.

The new task config declares its named *handles* in a ``[gate.bind]`` /
``[rubric.bind]`` table - one entry per handle, the value a *binding* that the
:func:`~coding_agent_playbook.evals._expr.compile_expr` interpreter later
references by name. This module is the **Factory** that turns each binding into a
concrete :class:`~coding_agent_playbook.evaluators.check.Check`, and (because the
boolean-group bindings recurse) a **Composite** builder over the
:mod:`coding_agent_playbook.evaluators.checks.compose` tree.

A binding (and any nested child) is exactly one of five mutually exclusive
shape-keys:

* **boolean group** - ``{all_of = [<binding>, …]}`` / ``{any_of = […]}`` /
  ``{not = <binding>}`` -> :class:`~coding_agent_playbook.evaluators.checks.compose.AllOf`
  / :class:`~coding_agent_playbook.evaluators.checks.compose.AnyOf` /
  :class:`~coding_agent_playbook.evaluators.checks.compose.Not` over the
  recursively-built children;
* **rubric group** - ``{rubric = [{judge="…", weight=…}, …], fail = 0.8}`` -> a
  :class:`~coding_agent_playbook.evaluators.rubric.Rubric` built by
  :meth:`Rubric.of <coding_agent_playbook.evaluators.rubric.Rubric.of>` (weighted
  :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`\\ s, weights
  normalized to sum ``1.0``), then **wrapped** as a boolean in a
  :class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` (``warn``/``fail``
  on the rubric's ``0-1`` composite) - a rubric *is* a ``Metric``, so it thresholds;
* **standalone check** - ``{check = "threshold"|"file_exists"|…, …kwargs}`` ->
  :func:`~coding_agent_playbook.evaluators.checks.registry.get_check`;
* **ref** - ``{ref = "name"}`` -> the gate registry
  (:func:`~coding_agent_playbook.evaluators.gates.get_gate`) when ``layer ==
  "gate"``, else the named-rubric registry
  (:func:`~coding_agent_playbook.evaluators.rubrics.get_rubric`).

Handles are all **boolean** checks: weights live only *inside* a rubric group's
``JudgeCheck``\\ s, never on a handle itself. The ``0-1`` thresholds from C3 are
already in effect, so ``fail=0.5`` is a normalized-score cutoff.

Acyclic by construction: this module imports from :mod:`coding_agent_playbook.evaluators`
only (the registries, ``compose``, ``Rubric``, ``ThresholdCheck``) - never the
reverse. It is purely additive (Track C5) - nothing in the task pipeline consumes
it yet (Track C7 wires it into the parser).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evaluators.check import ThresholdCheck
from coding_agent_playbook.evaluators.checks import compose
from coding_agent_playbook.evaluators.checks.registry import get_check
from coding_agent_playbook.evaluators.gates import get_gate
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.rubrics import get_rubric

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evaluators.check import Check

#: The five mutually-exclusive shape-keys a binding may carry, in dispatch order.
_SHAPE_KEYS = ("all_of", "any_of", "not", "rubric", "check", "ref")

#: Tolerance for the rubric-group weight-sum check (parity with the
#: ``[rubric].weights`` sum rule in :mod:`coding_agent_playbook.evals.task`).
_WEIGHT_SUM_TOLERANCE = 1e-3

#: The per-criterion ``JudgeCheck`` floor when a rubric group omits ``threshold``.
_DEFAULT_CRITERION_THRESHOLD = 0.5


def build_handles(
    bind_table: Mapping[str, Mapping[str, Any]],
    *,
    layer: str,
) -> dict[str, Check]:
    """Build the ``name -> Check`` map for a ``[<layer>.bind]`` table.

    Each top-level entry ``name`` maps to ``_build_one(binding, layer=layer,
    id=name)`` - the handle's id is its name so the compiled gate/rubric tree is
    readable. ``layer`` (``"gate"`` or ``"rubric"``) only steers the ``ref`` shape
    (which registry resolves it); every other shape is layer-agnostic.

    Almost every handle is a boolean :class:`Check`. The one exception is a
    rubric-layer ``ref`` (``layer="rubric"``, ``{ref = "name"}``), which resolves
    to the named :class:`Rubric` itself (a :class:`Metric`, not a boolean
    ``Check``) - the map value type stays ``Check`` for the common case, and a
    consumer that allows a rubric-ref handle widens locally.
    """
    return {name: _build_one(binding, layer=layer, id=name) for name, binding in bind_table.items()}


def _build_one(binding: Mapping[str, Any], *, layer: str, id: str) -> Check:
    """Build one handle from ``binding``, dispatching on its shape-key.

    Exactly one of :data:`_SHAPE_KEYS` must be present; zero or more than one is a
    :exc:`ValueError`. Boolean groups recurse (children get a namespaced ``id``);
    the rubric group builds a :class:`Rubric` and wraps it in a
    :class:`ThresholdCheck`; ``check`` routes through the check registry; ``ref``
    resolves via the gate or rubric registry per ``layer``.

    All branches return a boolean :class:`Check` except a rubric-layer ``ref``,
    which returns the bare named :class:`Rubric` (a :class:`Metric`) - that one
    value is widened from ``Check`` via the ``# type: ignore`` on the return, the
    single sanctioned spot where a handle is not yet a boolean.
    """
    shape = _shape_key(binding)

    if shape == "all_of":
        return compose.AllOf(*_build_children(binding["all_of"], layer=layer, id=id), id=id)
    if shape == "any_of":
        return compose.AnyOf(*_build_children(binding["any_of"], layer=layer, id=id), id=id)
    if shape == "not":
        child = _build_one(binding["not"], layer=layer, id=f"{id}!")
        return compose.Not(child, id=id)
    if shape == "rubric":
        return _build_rubric_group(binding, id=id)
    if shape == "check":
        kwargs = {k: v for k, v in binding.items() if k != "check"}
        return get_check(binding["check"], **kwargs)
    # shape == "ref": a gate ref resolves to a composed boolean Check directly; a
    # rubric ref resolves to the named Rubric (a Metric) and is wrapped in a
    # ThresholdCheck so its 0-1 composite becomes a boolean composable in the layer
    # expression - exactly like an inline rubric group. ``warn``/``fail`` override
    # the default composite floor.
    name = binding["ref"]
    if layer == "gate":
        return get_gate(name)
    return ThresholdCheck(
        get_rubric(name),
        warn=binding.get("warn"),
        fail=binding.get("fail", _DEFAULT_CRITERION_THRESHOLD),
    )


def _shape_key(binding: Mapping[str, Any]) -> str:
    """Return the single present shape-key, raising on zero or more than one.

    The error names every shape-key seen so a misconfigured binding (e.g. a
    ``check`` *and* a ``ref``) points the author at the conflict.
    """
    present = [key for key in _SHAPE_KEYS if key in binding]
    if len(present) != 1:
        raise ValueError(
            "a handle binding must carry exactly one of "
            f"{', '.join(_SHAPE_KEYS)} (got {present or 'none'})"
        )
    return present[0]


def _build_children(
    children: list[Mapping[str, Any]],
    *,
    layer: str,
    id: str,
) -> list[Check]:
    """Recursively build a boolean group's children with namespaced ids.

    Each child's id is ``"{id}[{i}]"`` so a nested tree's check ids stay readable
    and unique under the parent handle.
    """
    return [_build_one(child, layer=layer, id=f"{id}[{i}]") for i, child in enumerate(children)]


def _build_rubric_group(binding: Mapping[str, Any], *, id: str) -> ThresholdCheck:
    """Build a rubric group: ``Rubric.of(...)`` wrapped in a :class:`ThresholdCheck`.

    The criteria are ``(judge, weight)`` pairs; their weights must sum to ``1.0``
    (± :data:`_WEIGHT_SUM_TOLERANCE`) - mirroring the ``[rubric].weights`` sum rule
    - or this raises a :exc:`ValueError` (``Rubric.of`` would otherwise silently
    re-normalize). ``threshold`` (default :data:`_DEFAULT_CRITERION_THRESHOLD`) is
    the per-criterion ``JudgeCheck`` floor; ``warn``/``fail`` are the ``0-1``
    cutoffs on the rubric's composite, applied by the wrapping ``ThresholdCheck``
    (a rubric *is* a ``Metric``, so it thresholds).
    """
    criteria_raw = binding["rubric"]
    criteria = [(str(c["judge"]), float(c["weight"])) for c in criteria_raw]

    total = sum(weight for _, weight in criteria)
    if criteria and abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"rubric criteria weights must sum to 1.0 (±{_WEIGHT_SUM_TOLERANCE}), got {total}"
        )

    rubric = Rubric.of(
        *criteria,
        name=id,
        threshold=float(binding.get("threshold", _DEFAULT_CRITERION_THRESHOLD)),
    )
    warn = binding.get("warn")
    fail = binding.get("fail")
    return ThresholdCheck(
        rubric,
        warn=None if warn is None else float(warn),
        fail=None if fail is None else float(fail),
    )


__all__ = ["build_handles"]
