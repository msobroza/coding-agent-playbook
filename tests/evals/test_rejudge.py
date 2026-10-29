"""``evals.rejudge``: one stored run plus new criterion scores give the run's scores (spec D9).

The anchor property: re-scoring a run from what its answers line stores (the
judge-free checks, built by the record's own ``judge_free_checks``) and the
criterion scores its judge returned reproduces the run's ``passed``,
``aggregate_score`` and check scores exactly as the engine's ``score()`` made them.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands._eval_record_answers import judge_free_checks
from coding_agent_playbook.evals.answers_store import (
    JUDGE_PART_KEYS,
    CapturingJudge,
    judge_parts_of,
)
from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evals.rejudge import RejudgeError, rescore_run, rubric_criteria
from coding_agent_playbook.evals.release_metrics import run_check_scores
from coding_agent_playbook.evals.run.fake_runner import FakeRunner, write_files
from coding_agent_playbook.evals.sample import EvalSample
from coding_agent_playbook.evals.task_registry import load_task_sample
from coding_agent_playbook.exit_two import ExitTwoError
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.run.harness_runner import SampleResult

_SPOT = "review/spot-the-bug"
_CRBUG = "review/crbug-basic-auth-not"
_PRICING = "characterize/legacy-pricing"

#: A characterization test that passes on the shipped pricing module.
_PRICING_TEST = """\
from src.pricing import line_total


def test_ten_units_pay_full_price():
    assert line_total(100, 10) == 1000
"""

#: Each sample's fake agent: one whose gate passes.
_RUNNERS = {
    _SPOT: lambda: FakeRunner(transcript="paginate drops the last item"),
    _CRBUG: lambda: FakeRunner(transcript="`!` is not Python.\nVerdict: request changes\n"),
    _PRICING: lambda: FakeRunner(
        write_files({"tests/__init__.py": "", "tests/test_pricing.py": _PRICING_TEST})
    ),
}


def _sample(sample_id: str) -> EvalSample:
    return load_task_sample(CORE_ROOT / "eval_samples" / sample_id, source_package="engine")


def _judge(sample: EvalSample, low: float) -> StubJudge:
    """Scores the criteria apart: ``low`` for the first, rising by 0.1 per criterion."""
    criteria = [text for text, _weight in rubric_criteria(sample)]
    return StubJudge({text: min(1.0, low + 0.1 * i) for i, text in enumerate(criteria)})


def _run(sample: EvalSample, tmp_path: Path, low: float) -> tuple[SampleResult, dict[str, float]]:
    """One graded run of ``sample`` and the mean score its judge gave each criterion."""
    judge = CapturingJudge(_judge(sample, low))
    result = _RUNNERS[sample.id]().run_sample(sample, tmp_path, judge=judge)
    texts = {criterion for criterion, _artifact, _score, _n in judge.calls}
    scores = {
        text: statistics.fmean(s for c, _a, s, _n in judge.calls if c == text) for text in texts
    }
    return result, scores


@pytest.mark.catalog
@pytest.mark.parametrize("low", [0.7, 0.1])
@pytest.mark.parametrize("sample_id", [_SPOT, _CRBUG, _PRICING])
def test_rescoring_with_the_recorded_scores_reproduces_the_run(
    sample_id: str, low: float, tmp_path: Path
) -> None:
    sample = _sample(sample_id)
    result, scores = _run(sample, tmp_path, low)

    rescored = rescore_run(sample, judge_free_checks(result), scores)

    assert rescored.passed == result.passed
    assert rescored.aggregate_score == result.aggregate_score
    assert rescored.checks == run_check_scores(result)


def _stored_gate(*, passed: bool) -> dict[str, float]:
    return {"gate": float(passed), "file_unchanged:src/pagination.py": float(passed)}


def _all(sample: EvalSample, score: float) -> dict[str, float]:
    return {text: score for text, _weight in rubric_criteria(sample)}


def test_lower_criterion_scores_fail_the_rubric() -> None:
    sample = _sample(_SPOT)

    rescored = rescore_run(sample, _stored_gate(passed=True), _all(sample, 0.2))

    assert rescored.gate_passed is True
    assert rescored.rubric_passed is False
    assert rescored.rubric_score == pytest.approx(0.2)
    assert rescored.passed is False
    assert rescored.aggregate_score == 0.0


def test_high_criterion_scores_pass_the_rubric() -> None:
    sample = _sample(_SPOT)

    rescored = rescore_run(sample, _stored_gate(passed=True), _all(sample, 0.9))

    assert (rescored.rubric_passed, rescored.passed) == (True, True)
    assert rescored.checks["threshold:quality"] == pytest.approx(0.9)
    assert rescored.checks["file_unchanged:src/pagination.py"] == 1.0


def test_a_failed_gate_stays_failed_whatever_the_scores() -> None:
    sample = _sample(_SPOT)

    rescored = rescore_run(sample, _stored_gate(passed=False), _all(sample, 1.0))

    assert rescored.gate_passed is False
    assert rescored.rubric_passed is True
    assert rescored.passed is False
    assert rescored.aggregate_score == 0.0


def test_a_missing_criterion_score_names_the_criterion() -> None:
    sample = _sample(_SPOT)
    scores = _all(sample, 0.9)
    missing = next(iter(scores))
    del scores[missing]

    with pytest.raises(RejudgeError, match="no criterion score") as caught:
        rescore_run(sample, _stored_gate(passed=True), scores)
    assert missing in str(caught.value)


#: A gate that passes iff the agent wrote ``m.py``.
_MADE_GATE = {"expr": "made", "bind": {"made": {"check": "file_exists", "path": "m.py"}}}
#: A judged layer mixing a rubric group with a negated deterministic leaf.
_MIXED_RUBRIC = {
    "expr": "quality and not stray",
    "bind": {
        "quality": {"fail": 0.5, "rubric": [{"judge": "names the bug", "weight": 1.0}]},
        "stray": {"check": "file_exists", "path": "stray.py"},
    },
}


def _synthetic(tmp_path: Path, **blocks: object) -> EvalSample:
    data = {"id": "t-rejudge", "description": "rejudge fixture", **blocks}
    return EvalSample.from_dict(
        data, source_path=tmp_path / "sample.toml", prompt_id="refactor", source_package="<test>"
    )


@pytest.mark.parametrize(("files", "score"), [({"m.py": ""}, 0.8), ({"stray.py": ""}, 0.8)])
def test_a_judged_layer_reads_its_deterministic_leaves_from_the_stored_checks(
    files: dict[str, str], score: float, tmp_path: Path
) -> None:
    sample = _synthetic(tmp_path, gate=_MADE_GATE, rubric=_MIXED_RUBRIC)
    judge = CapturingJudge(StubJudge(default=score))
    result = FakeRunner(write_files(files)).run_sample(
        sample, tmp_path / "run", judge=judge, fail_fast=False
    )

    rescored = rescore_run(sample, judge_free_checks(result), {"names the bug": score})

    assert (rescored.passed, rescored.aggregate_score) == (result.passed, result.aggregate_score)
    assert rescored.checks == run_check_scores(result)
    assert rescored.rubric_passed is ("stray.py" not in files)


def test_a_partial_deterministic_score_in_a_judged_layer_is_refused(tmp_path: Path) -> None:
    sample = _synthetic(tmp_path, gate=_MADE_GATE, rubric=_MIXED_RUBRIC)
    stored = {"gate": 1.0, "file_exists:m.py": 1.0, "file_exists:stray.py": 0.5}

    with pytest.raises(RejudgeError, match=r"file_exists:stray\.py.*0\.5"):
        rescore_run(sample, stored, {"names the bug": 0.9})


def test_a_sample_with_an_aggregate_block_is_refused(tmp_path: Path) -> None:
    aggregate = {
        "expr": "rel",
        "bind": {"rel": {"metric": "pass_at_k", "k": 3, "over": "verdict", "fail": 0.5}},
    }
    sample = _synthetic(tmp_path, verdict={"trial": "gate"}, gate=_MADE_GATE, aggregate=aggregate)

    with pytest.raises(RejudgeError, match="t-rejudge") as caught:
        rescore_run(sample, {"gate": 1.0}, {})
    assert isinstance(caught.value, ExitTwoError)


def test_a_weighted_verdict_is_refused(tmp_path: Path) -> None:
    verdict = {"weights": {"gate": 0.5, "rubric": 0.5}, "fail": 0.5}
    sample = _synthetic(tmp_path, verdict=verdict, gate=_MADE_GATE, rubric=_MIXED_RUBRIC)

    with pytest.raises(RejudgeError, match=r"t-rejudge.*weighted"):
        rescore_run(sample, {"gate": 1.0}, {"names the bug": 0.9})


def test_judge_parts_picks_the_five_judge_keys() -> None:
    setup = {key: f"v-{key}" for key in JUDGE_PART_KEYS} | {"harness": "fake", "model": "m"}

    assert judge_parts_of(setup) == {key: f"v-{key}" for key in JUDGE_PART_KEYS}
    assert judge_parts_of({}) == dict.fromkeys(JUDGE_PART_KEYS)
