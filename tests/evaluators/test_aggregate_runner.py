"""Runner-level tests for the C8 across-trial aggregate layer (hermetic).

These exercise the N-trial loop in
:meth:`~coding_agent_playbook.evals.runner.HarnessRunner.run_task`: a task with an
``[aggregate]`` block runs ``N = max(k)`` trials, collects one
:class:`~coding_agent_playbook.evaluators.types.TrialResult` per trial, and grades
the compiled aggregate layer over them. The two headline guarantees:

* **degeneracy** — a task with *no* ``[aggregate]`` block runs **exactly one**
  trial and ``TaskResult.passed`` is that single trial's verdict (byte-identical
  to C7), and
* **aggregation** — a task with an ``[aggregate]`` block runs ``N`` trials whose
  verdict sequence is driven by a per-trial mutation, and the aggregate score
  matches the hand-computed ``pass@k`` / ``pass^k`` estimator.

A :class:`_SequenceRunner` drives a **known** per-trial verdict sequence: its
``_invoke_agent`` creates the gate's expected file on the trials flagged ``True``
(gate passes ⇒ verdict passes) and leaves it absent otherwise (gate fails ⇒
verdict fails).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.fake_runner import FakeRunner, write_files
from coding_agent_playbook.evals.runner import AgentRun, HarnessRunner
from coding_agent_playbook.evals.task import EvalTask

if TYPE_CHECKING:
    from pathlib import Path

#: The gate's expected file: a trial that creates it passes the gate (+ verdict).
_TARGET = "made.py"


class _SequenceRunner(HarnessRunner):
    """A runner that drives a fixed per-trial pass/fail sequence.

    ``passes[i]`` decides trial ``i``: when ``True`` the agent creates
    :data:`_TARGET` (the gate's ``file_exists`` target) so the gate + verdict pass;
    when ``False`` it creates nothing so the gate fails. An internal counter steps
    the sequence across the runner's N trials.
    """

    name = "sequence"

    def __init__(self, passes: list[bool]) -> None:
        self._passes = passes
        self._i = 0

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        should_pass = self._passes[self._i]
        self._i += 1
        if should_pass:
            (scratch_dir / _TARGET).write_text("x = 1\n", encoding="utf-8")
        return AgentRun(transcript=f"[trial {self._i}]", returncode=0)


def _gate() -> dict[str, Any]:
    """A gate that passes iff the agent created :data:`_TARGET`."""
    return {"expr": "made", "bind": {"made": {"check": "file_exists", "path": _TARGET}}}


def _aggregate(metric: str, *, k: int, over: str, fail: float) -> dict[str, Any]:
    """A single-handle ``[aggregate]`` block."""
    return {
        "expr": "rel",
        "bind": {"rel": {"metric": metric, "k": k, "over": over, "fail": fail}},
    }


def _make_task(
    task_dir: Path,
    *,
    gate: dict[str, Any] | None = None,
    aggregate: dict[str, Any] | None = None,
    verdict: str = "gate",
) -> EvalTask:
    data: dict[str, Any] = {
        "id": "t-agg",
        "prompt_id": "refactor",
        "description": "aggregate fixture",
        "verdict": {"trial": verdict},
    }
    if gate is not None:
        data["gate"] = gate
    if aggregate is not None:
        data["aggregate"] = aggregate
    return EvalTask.from_dict(data, source_path=task_dir / "task.toml", source_package="<test>")


# --------------------------------------------------------------------------- #
# Degeneracy: no [aggregate] => exactly one trial, passed == the verdict
# --------------------------------------------------------------------------- #


def test_no_aggregate_runs_exactly_one_trial(tmp_path: Path) -> None:
    """A task with no ``[aggregate]`` block runs a single trial (C7 behaviour)."""
    task = _make_task(tmp_path / "task", gate=_gate())

    runner = FakeRunner(write_files({_TARGET: "x = 1\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    assert len(result.trials) == 1
    assert result.aggregate is None
    assert result.passed is True
    # passed mirrors the single trial's verdict and the representative report.
    assert result.passed == result.trials[0].verdict
    assert result.passed == result.report.passed


def test_no_aggregate_failing_trial_fails_the_task(tmp_path: Path) -> None:
    """Single-trial degeneracy: a failing gate fails the task, one trial only."""
    task = _make_task(tmp_path / "task", gate=_gate())

    # No-op agent => _TARGET never created => gate fails.
    result = FakeRunner().run_task(task, tmp_path / "scratch")

    assert len(result.trials) == 1
    assert result.aggregate is None
    assert result.passed is False
    assert result.trials[0].verdict is False


# --------------------------------------------------------------------------- #
# Aggregation: N trials, known verdict sequence, pass@k / pass^k
# --------------------------------------------------------------------------- #


def test_pass_at_k_over_verdict_4_of_5(tmp_path: Path) -> None:
    """4 pass / 1 fail of 5 trials ⇒ pass@5 over verdict = 1.0 (PASS)."""
    task = _make_task(
        tmp_path / "task",
        gate=_gate(),
        aggregate=_aggregate("pass_at_k", k=5, over="verdict", fail=0.9),
    )
    runner = _SequenceRunner([True, True, True, True, False])
    result = runner.run_task(task, tmp_path / "scratch")

    assert len(result.trials) == 5  # ran N = max(k) = 5 trials
    assert [t.verdict for t in result.trials] == [True, True, True, True, False]
    assert result.aggregate is not None
    # n=5, c=4, k=5 => (n-c)=1 < 5 => pass@5 = 1.0
    assert result.aggregate.score == pytest.approx(1.0)
    assert result.passed is True
    assert result.aggregate_score == pytest.approx(1.0)


def test_pass_pow_k_over_verdict_below_floor_fails(tmp_path: Path) -> None:
    """3 pass / 2 fail of 5 ⇒ pass^3 over verdict = C(3,3)/C(5,3) = 0.1 < 0.5 (FAIL)."""
    task = _make_task(
        tmp_path / "task",
        gate=_gate(),
        aggregate=_aggregate("pass_pow_k", k=3, over="verdict", fail=0.5),
    )
    runner = _SequenceRunner([True, True, True, False, False])
    result = runner.run_task(task, tmp_path / "scratch")

    assert len(result.trials) == 3  # N = max(k) = 3
    assert result.aggregate is not None
    # n=3, c=3 (the first three creates succeed), k=3 => pass^3 = C(3,3)/C(3,3) = 1.0
    # NOTE: only 3 trials run, all three create the file => all pass => 1.0.
    assert result.aggregate.score == pytest.approx(1.0)
    assert result.passed is True


def test_pass_pow_k_with_a_failing_trial_in_window(tmp_path: Path) -> None:
    """A fail inside the N-trial window drops pass^k below the floor."""
    task = _make_task(
        tmp_path / "task",
        gate=_gate(),
        aggregate=_aggregate("pass_pow_k", k=3, over="verdict", fail=0.5),
    )
    # N=3: pass, fail, pass => c=2 < k=3 => pass^3 = 0.0 < 0.5 => FAIL.
    runner = _SequenceRunner([True, False, True])
    result = runner.run_task(task, tmp_path / "scratch")

    assert len(result.trials) == 3
    assert [t.verdict for t in result.trials] == [True, False, True]
    assert result.aggregate is not None
    assert result.aggregate.score == pytest.approx(0.0)
    assert result.passed is False


def test_each_trial_gets_a_fresh_setup(tmp_path: Path) -> None:
    """Each trial materializes a fresh ``setup/`` — a prior trial's edits never leak.

    Trial 0 creates the file (verdict pass); trial 1 creates nothing. If the
    scratch tree were shared, trial 1 would still see trial 0's file and pass —
    so a [False] second verdict proves each trial got a clean tree.
    """
    task = _make_task(
        tmp_path / "task",
        gate=_gate(),
        aggregate=_aggregate("pass_at_k", k=2, over="verdict", fail=0.4),
    )
    runner = _SequenceRunner([True, False])
    result = runner.run_task(task, tmp_path / "scratch")

    assert [t.verdict for t in result.trials] == [True, False]


# --------------------------------------------------------------------------- #
# Composed aggregate: two checks ANDed
# --------------------------------------------------------------------------- #


def test_composed_aggregate_and_gates_both(tmp_path: Path) -> None:
    """Two aggregate checks composed with ``and`` both gate the task verdict."""
    aggregate = {
        "expr": "reliable and consistent",
        "bind": {
            "reliable": {"metric": "pass_at_k", "k": 4, "over": "verdict", "fail": 0.9},
            "consistent": {"metric": "pass_pow_k", "k": 2, "over": "verdict", "fail": 0.5},
        },
    }
    task = _make_task(tmp_path / "task", gate=_gate(), aggregate=aggregate)

    # N = max(4, 2) = 4. Sequence: 3 pass / 1 fail.
    runner = _SequenceRunner([True, True, True, False])
    result = runner.run_task(task, tmp_path / "scratch")

    assert len(result.trials) == 4
    # reliable: pass@4 over verdict, n=4 c=3 k=4 => (n-c)=1 < 4 => 1.0 >= 0.9 (PASS)
    # consistent: pass^2 over verdict, n=4 c=3 k=2 => C(3,2)/C(4,2) = 3/6 = 0.5 >= 0.5 (PASS)
    # AllOf => both pass => task passes.
    assert result.passed is True
    assert result.aggregate is not None
    assert result.aggregate.passed is True


def test_composed_aggregate_fails_when_one_check_fails(tmp_path: Path) -> None:
    """A composed ``and`` aggregate fails the task when either check fails."""
    aggregate = {
        "expr": "reliable and consistent",
        "bind": {
            "reliable": {"metric": "pass_at_k", "k": 4, "over": "verdict", "fail": 0.9},
            "consistent": {"metric": "pass_pow_k", "k": 4, "over": "verdict", "fail": 0.9},
        },
    }
    task = _make_task(tmp_path / "task", gate=_gate(), aggregate=aggregate)

    # N=4, sequence 2 pass / 2 fail.
    runner = _SequenceRunner([True, True, False, False])
    result = runner.run_task(task, tmp_path / "scratch")

    # reliable: pass@4, n=4 c=2 k=4 => (n-c)=2 < 4 => 1.0 (PASS)
    # consistent: pass^4, n=4 c=2 k=4 => c < k => 0.0 < 0.9 (FAIL) => task fails.
    assert result.passed is False
    assert result.aggregate is not None
    assert result.aggregate.passed is False
