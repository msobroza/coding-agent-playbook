"""Tests for the deterministic ``answer_matches`` check (``evals/checks/answer.py``).

Unlike the file checks (which read ``ctx.tree``), this one grades the **graded
artifact** — ``ctx.artifact`` — so a review-only task, whose agent produces no
diff at all, can still be gated deterministically on what the agent *said*.

The gate is deliberately **fail-closed**: it is always ``available`` (it needs no
judge, project, or tree), so a missing/empty artifact grades ``False`` rather than
being skipped as unavailable — a skipped check is neutral in the layer expression
and would let a silent agent through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.checks.answer import AnswerMatchesCheck
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.checks.registry import get_check
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import CheckResult, EvalContext, ScopeDetail

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import Measurement


def _ms() -> MeasurementSet:
    """An empty measurement set — the answer check ignores measurements."""
    candidate: list[Measurement] = []
    return MeasurementSet(candidate, None)


def _ctx(artifact: object | None) -> EvalContext:
    return EvalContext(module=None, source="", label="rubric", artifact=artifact)


def _details(result: CheckResult) -> list[ScopeDetail]:
    """Narrow a result's ``subresults`` to its leaf :class:`ScopeDetail` rows."""
    details = [row for row in result.subresults if isinstance(row, ScopeDetail)]
    assert len(details) == len(result.subresults)
    return details


# --------------------------------------------------------------------------- #
# Descriptors
# --------------------------------------------------------------------------- #


def test_descriptors_match_the_other_deterministic_gates() -> None:
    check = AnswerMatchesCheck(r"(?i)command injection")
    assert check.determinism is Determinism.DETERMINISTIC
    assert check.cost is CostTier.DETERMINISTIC
    assert check.required is True
    assert check.weight == 0.0


def test_id_keys_on_the_pattern() -> None:
    assert AnswerMatchesCheck(r"(?i)cwe-78").id == "answer_matches:/(?i)cwe-78/"


def test_two_patterns_do_not_collide() -> None:
    assert AnswerMatchesCheck("a").id != AnswerMatchesCheck("b").id


# --------------------------------------------------------------------------- #
# available() — always on (fail-closed), unlike the tree-gated file checks
# --------------------------------------------------------------------------- #


def test_available_without_judge_project_or_tree() -> None:
    """No judge, no project, no tree, no artifact — still available."""
    assert AnswerMatchesCheck("x").available(_ctx(None)) is True


# --------------------------------------------------------------------------- #
# grade() — the predicate
# --------------------------------------------------------------------------- #


def test_match_passes() -> None:
    result = AnswerMatchesCheck(r"(?i)command injection").grade(
        _ctx("The flaw is an OS Command Injection reachable from the mailbox path."), _ms()
    )
    assert result.passed is True
    assert result.score == 1.0
    assert _details(result)[0].level == "ok"


def test_no_match_fails() -> None:
    result = AnswerMatchesCheck(r"(?i)command injection").grade(
        _ctx("The flaw is a SQL injection in the query builder."), _ms()
    )
    assert result.passed is False
    assert result.score == 0.0
    assert _details(result)[0].level == "fail"


def test_alternation_matches_any_branch() -> None:
    check = AnswerMatchesCheck(r"(?i)command injection|cwe[-\s]?78|os command")
    for answer in ("classified as CWE-78", "CWE 78 applies", "an OS command is built"):
        assert check.grade(_ctx(answer), _ms()).passed is True


def test_missing_artifact_grades_fail_not_error() -> None:
    """Fail-closed: a silent agent must lose the gate, not skip it."""
    result = AnswerMatchesCheck("x").grade(_ctx(None), _ms())
    assert result.passed is False
    assert result.score == 0.0


def test_empty_artifact_grades_fail() -> None:
    assert AnswerMatchesCheck("x").grade(_ctx(""), _ms()).passed is False


def test_non_string_artifact_is_stringified() -> None:
    """``ctx.artifact`` is typed ``Any``; the check must not assume ``str``."""
    assert AnswerMatchesCheck("42").grade(_ctx(42), _ms()).passed is True


def test_result_carries_the_check_id_and_one_detail() -> None:
    check = AnswerMatchesCheck("x")
    result = check.grade(_ctx("x"), _ms())
    assert result.check_id == check.id
    assert result.status == "run"
    assert len(_details(result)) == 1


# --------------------------------------------------------------------------- #
# Construction errors — a bad regex fails at build time, not grade time
# --------------------------------------------------------------------------- #


def test_invalid_regex_raises_naming_the_pattern() -> None:
    with pytest.raises(ValueError, match=r"\(unclosed"):
        AnswerMatchesCheck("(unclosed")


# --------------------------------------------------------------------------- #
# Registry wiring — resolvable as a ``[gate.bind]`` handle
# --------------------------------------------------------------------------- #


def test_registered_under_answer_matches() -> None:
    check = get_check("answer_matches", pattern=r"(?i)ssrf")
    assert isinstance(check, AnswerMatchesCheck)
    assert check.grade(_ctx("This is an SSRF."), _ms()).passed is True


def test_registry_accepts_weight_and_required_overrides() -> None:
    check = get_check("answer_matches", pattern="x", weight=0.5, required=False)
    assert check.weight == 0.5
    assert check.required is False
