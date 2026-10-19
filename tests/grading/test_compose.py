"""Tests for the boolean composer checks (T4b) - ``grading/compose.py``.

:class:`~coding_agent_playbook.grading.compose.AllOf` /
:class:`~coding_agent_playbook.grading.compose.AnyOf` /
:class:`~coding_agent_playbook.grading.compose.Not` are
:class:`~coding_agent_playbook.grading.check.Check`\\ s that compose child
checks through the cost-tiered short-circuit
:func:`~coding_agent_playbook.grading.scheduler.schedule`. These drive them
with a tiny fixed-verdict leaf check and assert: the AND/OR/NOT truth tables, the
neutral treatment of an **unavailable** child (skipped, not a failure - except
``Not`` over an unavailable child is itself skipped), the derived ``cost`` /
``determinism`` (``max`` child cost; JUDGED iff any child is JUDGED), that
``subresults`` carry the child :class:`~coding_agent_playbook.grading.types.CheckResult`\\ s,
and nesting a composer inside a composer.
"""

from __future__ import annotations

from coding_agent_playbook.grading.check import Check, MeasurementSet
from coding_agent_playbook.grading.compose import AllOf, AnyOf, Not
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, EvalContext


def _ctx() -> EvalContext:
    return EvalContext(module=None, source="", label="compose")


def _empty() -> MeasurementSet:
    return MeasurementSet([], None)


class _Leaf(Check):
    """A fixed-verdict leaf check with configurable cost/determinism/availability."""

    def __init__(
        self,
        tag: str,
        *,
        passed: bool,
        cost: CostTier = CostTier.DETERMINISTIC,
        determinism: Determinism = Determinism.DETERMINISTIC,
        avail: bool = True,
    ) -> None:
        self.id = tag
        self._passed = passed
        self.cost = cost
        self.determinism = determinism
        self.weight = 0.0
        self.required = True
        self._avail = avail

    def available(self, ctx: EvalContext) -> bool:
        return self._avail

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        return CheckResult(
            check_id=self.id,
            passed=self._passed,
            score=1.0 if self._passed else 0.0,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=(),
        )


def _run(check: Check) -> CheckResult:
    return check.grade(_ctx(), _empty())


# --------------------------------------------------------------------------- #
# AllOf truth table.
# --------------------------------------------------------------------------- #


def test_allof_all_pass() -> None:
    result = _run(AllOf(_Leaf("a", passed=True), _Leaf("b", passed=True)))
    assert result.passed is True
    assert result.score == 1.0
    assert result.status == "run"
    assert result.check_id == "all_of"


def test_allof_one_fails() -> None:
    result = _run(AllOf(_Leaf("a", passed=True), _Leaf("b", passed=False)))
    assert result.passed is False
    assert result.score == 0.0


def test_allof_empty_is_vacuously_true() -> None:
    result = _run(AllOf())
    assert result.passed is True
    assert result.score == 1.0


def test_allof_unavailable_child_is_neutral() -> None:
    # An unavailable child is skipped (neutral), not a failure: the available
    # passing child carries the verdict.
    result = _run(AllOf(_Leaf("a", passed=True), _Leaf("b", passed=False, avail=False)))
    assert result.passed is True
    # subresults carry the child rows; the unavailable one is skipped.
    by_id = {r.check_id: r for r in result.subresults if isinstance(r, CheckResult)}
    assert by_id["a"].status == "run"
    assert by_id["b"].status == "skipped"


def test_allof_all_children_unavailable_is_skipped() -> None:
    # No child can run ⇒ the composer has no verdict ⇒ it is itself skipped
    # (neutral), never a vacuous pass. Regression: the [rubric] layer with no
    # judge used to report "[PASS] rubric (score=1.000)", and so made
    # `gate or rubric` pass on a failing gate.
    composer = AllOf(_Leaf("a", passed=False, avail=False))
    assert composer.available(_ctx()) is False
    result = _run(composer)
    assert result.status == "skipped"
    assert result.passed is False
    assert result.score is None
    (child,) = result.subresults
    assert isinstance(child, CheckResult)
    assert child.status == "skipped"


def test_anyof_all_children_unavailable_is_skipped() -> None:
    # Regression: an all-unavailable AnyOf used to *fail* (no run child passed),
    # so a judge-only `a or b` rubric layer failed outright with no judge.
    composer = AnyOf(_Leaf("a", passed=True, avail=False), _Leaf("b", passed=True, avail=False))
    assert composer.available(_ctx()) is False
    assert _run(composer).status == "skipped"


def test_composer_is_available_when_any_child_is() -> None:
    composer = AllOf(_Leaf("a", passed=True), _Leaf("b", passed=False, avail=False))
    assert composer.available(_ctx()) is True


def test_skip_propagates_through_nested_composers() -> None:
    inner = AnyOf(_Leaf("a", passed=True, avail=False), id="inner")
    outer = AllOf(inner, Not(_Leaf("b", passed=True, avail=False)), id="outer")
    assert inner.available(_ctx()) is False
    assert outer.available(_ctx()) is False
    assert _run(outer).status == "skipped"


def test_not_is_available_iff_its_child_is() -> None:
    assert Not(_Leaf("a", passed=True)).available(_ctx()) is True
    assert Not(_Leaf("a", passed=True, avail=False)).available(_ctx()) is False


def test_childless_composers_keep_their_vacuous_verdicts() -> None:
    # Nothing to be neutral about: an empty AllOf is True, an empty AnyOf False.
    assert AllOf().available(_ctx()) is True
    assert AnyOf().available(_ctx()) is True
    assert _run(AllOf()).passed is True
    assert _run(AnyOf()).passed is False
    assert _run(AnyOf()).status == "run"


# --------------------------------------------------------------------------- #
# AnyOf truth table.
# --------------------------------------------------------------------------- #


def test_anyof_one_passes() -> None:
    result = _run(AnyOf(_Leaf("a", passed=False), _Leaf("b", passed=True)))
    assert result.passed is True
    assert result.score == 1.0
    assert result.check_id == "any_of"


def test_anyof_none_pass() -> None:
    result = _run(AnyOf(_Leaf("a", passed=False), _Leaf("b", passed=False)))
    assert result.passed is False
    assert result.score == 0.0


def test_anyof_empty_is_false() -> None:
    # No child ran ⇒ no pass ⇒ AnyOf is False.
    result = _run(AnyOf())
    assert result.passed is False


def test_anyof_unavailable_child_is_neutral() -> None:
    result = _run(AnyOf(_Leaf("a", passed=False, avail=False), _Leaf("b", passed=True)))
    assert result.passed is True
    by_id = {r.check_id: r for r in result.subresults if isinstance(r, CheckResult)}
    assert by_id["a"].status == "skipped"
    assert by_id["b"].status == "run"


# --------------------------------------------------------------------------- #
# Not truth table.
# --------------------------------------------------------------------------- #


def test_not_inverts_a_pass() -> None:
    result = _run(Not(_Leaf("a", passed=True)))
    assert result.passed is False
    assert result.score == 0.0
    assert result.check_id == "not"


def test_not_inverts_a_fail() -> None:
    result = _run(Not(_Leaf("a", passed=False)))
    assert result.passed is True
    assert result.score == 1.0


def test_not_over_unavailable_child_is_skipped() -> None:
    # The single child could not run ⇒ Not has nothing to invert ⇒ skipped.
    result = _run(Not(_Leaf("a", passed=True, avail=False)))
    assert result.status == "skipped"
    assert result.passed is False
    assert result.score is None
    (child,) = result.subresults
    assert isinstance(child, CheckResult)
    assert child.check_id == "a"
    assert child.status == "skipped"


# --------------------------------------------------------------------------- #
# subresults carry the child CheckResults.
# --------------------------------------------------------------------------- #


def test_subresults_carry_child_results() -> None:
    result = _run(AllOf(_Leaf("a", passed=True), _Leaf("b", passed=False)))
    assert len(result.subresults) == 2
    assert all(isinstance(r, CheckResult) for r in result.subresults)
    assert [r.check_id for r in result.subresults if isinstance(r, CheckResult)] == ["a", "b"]


# --------------------------------------------------------------------------- #
# cost / determinism derivation.
# --------------------------------------------------------------------------- #


def test_cost_is_max_child_cost() -> None:
    composer = AllOf(
        _Leaf("a", passed=True, cost=CostTier.DETERMINISTIC),
        _Leaf("b", passed=True, cost=CostTier.EXECUTION),
    )
    assert composer.cost is CostTier.EXECUTION


def test_cost_defaults_deterministic_with_no_children() -> None:
    assert AllOf().cost is CostTier.DETERMINISTIC
    assert AnyOf().cost is CostTier.DETERMINISTIC


def test_determinism_is_judged_iff_a_child_is_judged() -> None:
    deterministic = AllOf(
        _Leaf("a", passed=True, determinism=Determinism.DETERMINISTIC),
        _Leaf("b", passed=True, determinism=Determinism.DETERMINISTIC),
    )
    assert deterministic.determinism is Determinism.DETERMINISTIC

    judged = AllOf(
        _Leaf("a", passed=True, determinism=Determinism.DETERMINISTIC),
        _Leaf(
            "b",
            passed=True,
            cost=CostTier.JUDGED,
            determinism=Determinism.JUDGED,
        ),
    )
    assert judged.determinism is Determinism.JUDGED
    assert judged.cost is CostTier.JUDGED


def test_not_derives_cost_and_determinism_from_its_child() -> None:
    composer = Not(_Leaf("a", passed=True, cost=CostTier.JUDGED, determinism=Determinism.JUDGED))
    assert composer.cost is CostTier.JUDGED
    assert composer.determinism is Determinism.JUDGED


# --------------------------------------------------------------------------- #
# Descriptors + nesting.
# --------------------------------------------------------------------------- #


def test_default_descriptors() -> None:
    composer = AllOf(_Leaf("a", passed=True))
    assert composer.id == "all_of"
    assert composer.weight == 0.0
    assert composer.required is True
    assert AnyOf(_Leaf("a", passed=True)).id == "any_of"
    assert Not(_Leaf("a", passed=True)).id == "not"


def test_custom_id_weight_required() -> None:
    composer = AllOf(_Leaf("a", passed=True), id="my_gate", weight=2.0, required=False)
    assert composer.id == "my_gate"
    assert composer.weight == 2.0
    assert composer.required is False


def test_nested_composers() -> None:
    # AllOf(leaf, AnyOf(fail, pass)) ⇒ inner AnyOf passes ⇒ outer AllOf passes.
    inner = AnyOf(_Leaf("x", passed=False), _Leaf("y", passed=True))
    outer = AllOf(_Leaf("a", passed=True), inner)
    result = _run(outer)
    assert result.passed is True
    assert result.score == 1.0

    # The outer subresults carry the leaf result + the inner composer's result.
    sub_ids = [r.check_id for r in result.subresults if isinstance(r, CheckResult)]
    assert sub_ids == ["a", "any_of"]
    inner_result = next(
        r for r in result.subresults if isinstance(r, CheckResult) and r.check_id == "any_of"
    )
    assert inner_result.passed is True
    # The inner composer's own subresults are its children.
    inner_sub_ids = [r.check_id for r in inner_result.subresults if isinstance(r, CheckResult)]
    assert inner_sub_ids == ["x", "y"]


def test_nested_allof_with_failing_inner_anyof() -> None:
    inner = AnyOf(_Leaf("x", passed=False), _Leaf("y", passed=False))
    outer = AllOf(_Leaf("a", passed=True), inner)
    result = _run(outer)
    assert result.passed is False
