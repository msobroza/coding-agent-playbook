"""End-to-end tests for the eval runner + scoring bridge (hermetic, C7).

Everything runs through :class:`~coding_agent_playbook.evals.fake_runner.FakeRunner`
so there is no network or agent CLI: a fixture lays down a ``setup/`` tree (a long
function + a passing test), then different fake mutations stand in for an agent's
edits and we assert the resulting :class:`EvaluationReport`.

C7 sources the checks from the **C6 compiler**: a task's ``[gate]``/``[rubric]``
blocks compile into one per-trial
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` carrying the two named
layer checks (``id="gate"`` / ``id="rubric"``); the per-trial **verdict** is then
derived from the layer results (skipped-neutral) onto ``report.passed``. Metric
gates (CC, coverage, test_pass_rate) enter via ``threshold``/``non_regression``
*checks* inside the gate bind; the deterministic file predicates are the
``file_*`` checks; the judged criteria live in a ``rubric`` group inside the
``[rubric]`` bind.

These tests build the new-schema task dicts directly. The static-only tests are
fast; the execution-non-regression tests actually run an inner pytest and are
slower.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.fake_runner import FakeRunner, write_files
from coding_agent_playbook.evals.runner import (
    Baseline,
    Candidate,
    capture,
    materialize,
    render_prompt,
)
from coding_agent_playbook.evals.scoring import score
from coding_agent_playbook.evals.task import EvalTask, TaskInvocation
from coding_agent_playbook.evaluators import EvaluationReport
from coding_agent_playbook.evaluators.types import CheckResult, ScopeDetail

# A long, high-complexity function: lots of branches => high cyclomatic complexity.
_LONG_FN = textwrap.dedent(
    """\
    def classify(n):
        if n < 0:
            return "neg"
        if n == 0:
            return "zero"
        if n < 10:
            return "small"
        if n < 100:
            return "medium"
        if n < 1000:
            return "large"
        if n % 2 == 0:
            return "big-even"
        if n % 3 == 0:
            return "big-div3"
        return "big-other"
    """
)

# A refactor that *lowers* CC of ``classify`` by extracting the band lookup.
_REFACTORED = textwrap.dedent(
    """\
    _BANDS = (
        (0, "neg"),
        (1, "zero"),
        (10, "small"),
        (100, "medium"),
        (1000, "large"),
    )


    def _band(n):
        for ceiling, label in _BANDS:
            if n < ceiling:
                return label
        return None


    def classify(n):
        band = _band(n)
        return band if band is not None else "big"
    """
)

# A worsening mutation: even MORE branches than the baseline => CC goes up.
_WORSE = textwrap.dedent(
    """\
    def classify(n):
        if n < 0:
            return "neg"
        if n == 0:
            return "zero"
        if n < 10:
            return "small"
        if n < 100:
            return "medium"
        if n < 1000:
            return "large"
        if n % 2 == 0:
            return "big-even"
        if n % 3 == 0:
            return "big-div3"
        if n % 5 == 0:
            return "big-div5"
        if n % 7 == 0:
            return "big-div7"
        if n % 11 == 0:
            return "big-div11"
        return "big-other"
    """
)

_TEST_OK = textwrap.dedent(
    """\
    from mod import classify


    def test_small():
        assert classify(5) == "small"
    """
)


# --------------------------------------------------------------------------- #
# Report helpers — walk the report.checks → subresults shape (recursive)
# --------------------------------------------------------------------------- #


def _scope_details(report: EvaluationReport) -> list[ScopeDetail]:
    """Every per-scope :class:`ScopeDetail` leaf anywhere under the run checks."""
    out: list[ScopeDetail] = []

    def _walk(result: CheckResult) -> None:
        if result.status != "run":
            return
        for sub in result.subresults:
            if isinstance(sub, ScopeDetail):
                out.append(sub)
            elif isinstance(sub, CheckResult):
                _walk(sub)

    for check in report.checks:
        _walk(check)
    return out


def _scopes_for_evaluator(report: EvaluationReport, evaluator: str) -> list[ScopeDetail]:
    """Leaves whose ``evaluator`` matches (the metric name / check id)."""
    return [d for d in _scope_details(report) if d.evaluator == evaluator]


def _checks_by_id(report: EvaluationReport) -> dict[str, CheckResult]:
    """Flatten every :class:`CheckResult` (layers + their children) by id."""
    out: dict[str, CheckResult] = {}

    def _walk(result: CheckResult) -> None:
        out[result.check_id] = result
        for sub in result.subresults:
            if isinstance(sub, CheckResult):
                _walk(sub)

    for check in report.checks:
        _walk(check)
    return out


def _check(report: EvaluationReport, check_id: str) -> CheckResult:
    """The single :class:`CheckResult` with ``check_id`` anywhere in the tree."""
    return _checks_by_id(report)[check_id]


# --------------------------------------------------------------------------- #
# Setup / task fixtures (new C7 schema)
# --------------------------------------------------------------------------- #


def _make_setup(task_dir: Path, *, mod_source: str = _LONG_FN, test_source: str = _TEST_OK) -> None:
    """Lay down ``<task_dir>/setup/{mod.py,test_mod.py}``."""
    setup = task_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text(mod_source, encoding="utf-8")
    (setup / "test_mod.py").write_text(test_source, encoding="utf-8")


def _make_task(
    task_dir: Path,
    *,
    gate: dict[str, Any] | None = None,
    rubric: dict[str, Any] | None = None,
    verdict: str | None = None,
    invocation: TaskInvocation | None = None,
    prompt_id: str = "refactor",
) -> EvalTask:
    """Build an :class:`EvalTask` from the new-schema ``[gate]``/``[rubric]`` dicts.

    ``verdict`` defaults sensibly: ``"gate and rubric"`` when both blocks are
    present, ``"gate"`` for gate-only, ``"rubric"`` for rubric-only.
    """
    data: dict[str, Any] = {
        "id": "t-fixture",
        "prompt_id": prompt_id,
        "description": "fixture task",
    }
    if gate is not None:
        data["gate"] = gate
    if rubric is not None:
        data["rubric"] = rubric
    if verdict is None:
        if gate is not None and rubric is not None:
            verdict = "gate and rubric"
        elif gate is not None:
            verdict = "gate"
        else:
            verdict = "rubric"
    data["verdict"] = {"trial": verdict}
    task = EvalTask.from_dict(data, source_path=task_dir / "task.toml", source_package="<test>")
    if invocation is not None:
        task.invocation = invocation
    return task


def _cc_gate() -> dict[str, Any]:
    """A gate gating cyclomatic complexity on non-regression (0-1 cutoffs).

    The refactor's new ``_band`` (CC 3 -> score 1.0) clears ``warn=0.5`` so the good
    refactor still passes; a worsening edit fails on regression vs the baseline.
    """
    return {
        "expr": "cc",
        "bind": {
            "cc": {
                "check": "non_regression",
                "metric": "cyclomatic_complexity",
                "warn": 0.5,
                "fail": 0.25,
            }
        },
    }


def _judged_rubric(*criteria: str, fail: float = 0.5) -> dict[str, Any]:
    """A rubric group with uniform-weighted judged ``criteria``."""
    n = len(criteria)
    weight = 1.0 / n if n else 0.0
    return {
        "expr": "quality",
        "bind": {
            "quality": {
                "fail": fail,
                "rubric": [{"judge": c, "weight": weight} for c in criteria],
            }
        },
    }


# --------------------------------------------------------------------------- #
# Orchestration helpers
# --------------------------------------------------------------------------- #


def test_materialize_copies_setup_and_commits_baseline(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())
    scratch = tmp_path / "scratch"

    baseline = materialize(task, scratch)

    assert (scratch / "mod.py").is_file()
    assert (scratch / ".git").is_dir()
    assert baseline.commit  # a real SHA
    assert baseline.setup_snapshot != scratch
    assert (baseline.setup_snapshot / "mod.py").read_text() == _LONG_FN


def test_capture_includes_new_files_in_diff_and_changed(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())
    scratch = tmp_path / "scratch"
    baseline = materialize(task, scratch)

    (scratch / "new.py").write_text("x = 1\n", encoding="utf-8")
    candidate = capture(scratch, baseline, "transcript-here")

    assert "new.py" in candidate.changed_files
    assert "new.py" in candidate.diff
    assert candidate.transcript == "transcript-here"


def test_render_prompt_falls_back_for_unresolvable_prompt(tmp_path: Path) -> None:
    """A synthetic task with no ``resources/`` root resolves to a placeholder."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(
        task_dir,
        gate=_cc_gate(),
        invocation=TaskInvocation(prompt_args="do the thing"),
        prompt_id="nonexistent",
    )
    prompt = render_prompt(task)
    assert "nonexistent" in prompt
    assert "do the thing" in prompt


def test_render_prompt_resolves_a_real_shipped_prompt() -> None:
    """A task pointing at a shipped (non-templated) prompt renders its real body."""
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src" / "coding_agent_playbook"
    task_dir = src_root / "resources" / "eval_tasks" / "refactor-extract-helper"
    assert (task_dir / "task.toml").is_file()

    task = EvalTask(
        id="refactor-extract-helper",
        prompt_id="refactor",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="coding_agent_playbook",
        invocation=TaskInvocation(prompt_args="extract the totals block"),
    )
    prompt = render_prompt(task)
    assert "refactoring existing code" in prompt
    assert "extract the totals block" in prompt


# --------------------------------------------------------------------------- #
# FakeRunner round-trips (static metric gate, fast)
# --------------------------------------------------------------------------- #


def test_good_refactor_passes_and_cc_drops(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch")

    assert isinstance(result.report, EvaluationReport)
    assert result.passed is True
    assert result.harness == "fake"
    assert result.task_id == "t-fixture"

    cc_check = _check(result.report, "nonreg:cyclomatic_complexity")
    assert cc_check.passed is True
    classify = next(
        sub
        for sub in cc_check.subresults
        if isinstance(sub, ScopeDetail) and sub.scope_key.endswith("::classify")
    )
    assert classify.baseline is not None
    assert classify.value < classify.baseline
    assert classify.level == "ok"


def test_worsening_refactor_fails_with_regression_finding(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())

    runner = FakeRunner(write_files({"mod.py": _WORSE}))
    result = runner.run_task(task, tmp_path / "scratch")

    assert result.passed is False
    cc_check = _check(result.report, "nonreg:cyclomatic_complexity")
    assert cc_check.passed is False
    classify = next(
        sub
        for sub in cc_check.subresults
        if isinstance(sub, ScopeDetail) and sub.scope_key.endswith("::classify")
    )
    assert classify.level == "fail"
    assert classify.kind == "regression"
    assert classify.value > (classify.baseline or 0)


def test_absolute_mode_new_scope_uses_absolute_kind(tmp_path: Path) -> None:
    """A brand-new file (no baseline counterpart) grades absolute (kind=new)."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    # Threshold-only check (absolute mode) on a fresh file the baseline lacks.
    # 0-1 cutoffs: _WORSE's classify is CC 11 -> normalized score 0.6 < fail=0.7.
    gate = {
        "expr": "cc",
        "bind": {
            "cc": {
                "check": "threshold",
                "metric": "cyclomatic_complexity",
                "warn": 0.9,
                "fail": 0.7,
            }
        },
    }
    task = _make_task(task_dir, gate=gate)

    runner = FakeRunner(write_files({"extra.py": _WORSE}))
    result = runner.run_task(task, tmp_path / "scratch")

    cc_check = _check(result.report, "threshold:cyclomatic_complexity")
    classify = next(
        sub
        for sub in cc_check.subresults
        if isinstance(sub, ScopeDetail)
        and sub.scope_key.startswith("extra.py")
        and sub.scope_key.endswith("::classify")
    )
    assert classify.kind == "new"
    assert classify.level == "fail"  # score 0.6 < fail=0.7
    assert result.passed is False


# --------------------------------------------------------------------------- #
# Gate file checks
# --------------------------------------------------------------------------- #


def _file_gate() -> dict[str, Any]:
    """A gate ANDing one of each file predicate (some will fail under a refactor)."""
    return {
        "expr": "mod_exists and helper_exists and has_band and src_unchanged and not_forbidden",
        "bind": {
            "mod_exists": {"check": "file_exists", "path": "mod.py"},
            "helper_exists": {"check": "file_exists", "path": "helper.py"},
            "has_band": {"check": "file_contains", "path": "mod.py", "pattern": r"def _band"},
            "src_unchanged": {"check": "file_unchanged", "path": "mod.py"},
            "not_forbidden": {"check": "file_forbidden", "path": "test_mod.py"},
        },
    }


def test_gate_file_checks_merge_into_report(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_file_gate())

    # Agent: refactor mod.py (so it changes + contains _band) and add helper.py.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED, "helper.py": "x = 1\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    by_id = _checks_by_id(result.report)
    assert by_id["file_exists:mod.py"].passed is True  # exists
    assert by_id["file_exists:helper.py"].passed is True  # created
    assert by_id["file_contains:mod.py~/def _band/"].passed is True  # contains _band
    assert by_id["file_unchanged:mod.py"].passed is False  # rewritten by the refactor
    assert by_id["file_forbidden:test_mod.py"].passed is False  # present => breach

    # The gate ANDs them, so a single breach fails the gate (and the verdict).
    assert result.passed is False


def test_gate_all_passing_yields_a_passing_report(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    gate = {
        "expr": "helper_exists and answer and src_unchanged and no_nope",
        "bind": {
            "helper_exists": {"check": "file_exists", "path": "helper.py"},
            "answer": {"check": "file_contains", "path": "helper.py", "pattern": r"answer = 42"},
            "src_unchanged": {"check": "file_unchanged", "path": "mod.py"},
            "no_nope": {"check": "file_forbidden", "path": "nope.py"},
        },
    }
    task = _make_task(task_dir, gate=gate)

    runner = FakeRunner(write_files({"helper.py": "answer = 42\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    gate_check = _check(result.report, "gate")
    assert gate_check.passed is True
    assert result.passed is True


# --------------------------------------------------------------------------- #
# Execution non-regression (runs an inner pytest)
# --------------------------------------------------------------------------- #


def _exec_gate() -> dict[str, Any]:
    """A gate gating test_pass_rate + coverage on non-regression (execution metrics)."""
    return {
        "expr": "tpr and cov",
        "bind": {
            "tpr": {"check": "non_regression", "metric": "test_pass_rate"},
            "cov": {"check": "non_regression", "metric": "coverage"},
        },
    }


def test_execution_non_regression_passes_when_tests_stay_green(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_exec_gate())

    # A behaviour-preserving refactor: tests still pass.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch")

    tpr = _scopes_for_evaluator(result.report, "test_pass_rate")
    assert tpr, "expected a test_pass_rate scope leaf"
    assert all(d.level != "fail" for d in tpr)
    assert result.passed is True


def test_execution_non_regression_fails_when_a_test_breaks(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_exec_gate())

    broken = textwrap.dedent(
        """\
        def classify(n):
            return "WRONG"
        """
    )
    runner = FakeRunner(write_files({"mod.py": broken}))
    result = runner.run_task(task, tmp_path / "scratch")

    tpr = next(d for d in _scope_details(result.report) if d.evaluator == "test_pass_rate")
    assert tpr.baseline == pytest.approx(1.0)
    assert tpr.value < 1.0
    assert tpr.level == "fail"
    assert result.passed is False


# --------------------------------------------------------------------------- #
# Verdict + no-judge invariant
# --------------------------------------------------------------------------- #


def test_gate_only_verdict_equals_the_gate(tmp_path: Path) -> None:
    """A gate-only task's verdict is the gate layer's pass/fail."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(task, tmp_path / "scratch")
    gate = _check(result.report, "gate")
    assert result.passed == gate.passed


def test_deterministic_only_verdict_is_the_gate_when_rubric_skips(tmp_path: Path) -> None:
    """With no judge, the rubric layer's judged content skips; the verdict = gate.

    The rubric layer is present (``gate and rubric``) but its judged ThresholdCheck
    is unavailable without ``ctx.judge`` — so the verdict reduces to the gate
    (skipped-neutral): a passing gate => a passing trial.
    """
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity", "naming"))

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(task, tmp_path / "scratch")

    # The inner judged checks never ran (no judge).
    assert not any(d.evaluator.startswith("judge:") for d in _scope_details(result.report))
    gate = _check(result.report, "gate")
    assert gate.passed is True
    # Verdict == gate (rubric layer is skipped-neutral).
    assert result.passed is True


def test_score_is_callable_directly_with_handles(tmp_path: Path) -> None:
    """``score(task, baseline, candidate)`` works without going through run_task."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())

    baseline = materialize(task, tmp_path / "scratch")
    write_files({"mod.py": _REFACTORED})(baseline.repo_root)
    candidate = capture(baseline.repo_root, baseline, "transcript")
    assert isinstance(baseline, Baseline)
    assert isinstance(candidate, Candidate)

    report = score(task, baseline, candidate)
    assert report.passed is True


# --------------------------------------------------------------------------- #
# Judged [rubric] scoring (hermetic via StubJudge)
# --------------------------------------------------------------------------- #


def test_judged_rubric_passes_with_a_high_judge(tmp_path: Path) -> None:
    """A [rubric] task run via FakeRunner + a high StubJudge passes the rubric layer."""
    from coding_agent_playbook.evals.judge import StubJudge

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity", "naming"))

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(
        task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.9, "naming": 0.7})
    )

    rubric = _check(result.report, "rubric")
    assert rubric.status == "run"
    assert rubric.passed is True  # composite 0.8 >= 0.5 floor
    # The rubric layer wraps a ThresholdCheck over the judged rubric group; its
    # threshold leaf carries the rubric composite (mean of 0.9 and 0.7 == 0.8).
    threshold = _check(result.report, "threshold:quality")
    assert threshold.score == pytest.approx(0.8)
    assert result.passed is True


def test_low_judged_score_fails_the_rubric_layer_and_verdict(tmp_path: Path) -> None:
    """A rubric composite below the floor fails the rubric layer => verdict False."""
    from coding_agent_playbook.evals.judge import StubJudge

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity"))

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    # composite 0.3 < 0.5 floor => rubric layer fails.
    result = runner.run_task(task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.3}))

    rubric = _check(result.report, "rubric")
    assert rubric.passed is False
    # gate passes but rubric fails => "gate and rubric" verdict is False.
    assert _check(result.report, "gate").passed is True
    assert result.passed is False


def test_no_judge_preserves_deterministic_only_behaviour(tmp_path: Path) -> None:
    """With no judge, the rubric's judged content skips; the verdict = gate."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity", "naming"))

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(task, tmp_path / "scratch")

    assert not any(d.evaluator.startswith("judge:") for d in _scope_details(result.report))
    assert result.passed is True


def test_samples_threaded_through_to_the_judge(tmp_path: Path) -> None:
    """``run_task(samples=N)`` reaches the judge as the per-criterion ``n``."""
    from coding_agent_playbook.evals.judge import StubJudge

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, rubric=_judged_rubric("clarity"), verdict="rubric")

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(
        task, tmp_path / "scratch", judge=judge, samples=5
    )
    assert judge.calls == [("clarity", judge.calls[0][1], 5)]


def test_judge_artifact_is_the_candidate_diff(tmp_path: Path) -> None:
    """The judged artifact is the candidate's captured git diff (the agent's change)."""
    from coding_agent_playbook.evals.judge import StubJudge

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, rubric=_judged_rubric("clarity"), verdict="rubric")

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(write_files({"helper.py": "answer = 42\n"})).run_task(
        task, tmp_path / "scratch", judge=judge
    )
    _criterion, artifact, _n = judge.calls[0]
    assert "answer = 42" in str(artifact)


# --------------------------------------------------------------------------- #
# Fail-fast: a lost deterministic gate skips the judge tier
# --------------------------------------------------------------------------- #


def test_fail_fast_skips_the_judge_when_a_gate_check_fails(tmp_path: Path) -> None:
    """fail_fast (the runner default) skips the judge tier once the gate is lost."""
    from coding_agent_playbook.evals.judge import StubJudge

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    # A gate check the no-op agent will violate (the file is never created).
    gate = {
        "expr": "made",
        "bind": {"made": {"check": "file_exists", "path": "never_created.py"}},
    }
    task = _make_task(task_dir, gate=gate, rubric=_judged_rubric("clarity"))

    judge = StubJudge({"clarity": 0.9})
    result = FakeRunner().run_task(task, tmp_path / "scratch", judge=judge)

    assert result.passed is False
    # The judge was never invoked.
    assert judge.calls == []
    # The rubric layer is recorded skipped, not run.
    assert _check(result.report, "rubric").status == "skipped"


def test_full_scoring_runs_the_judge_even_after_a_failed_gate(tmp_path: Path) -> None:
    """fail_fast=False (``--full-scoring``) grades the judge tier regardless."""
    from coding_agent_playbook.evals.judge import StubJudge

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    gate = {
        "expr": "made",
        "bind": {"made": {"check": "file_exists", "path": "never_created.py"}},
    }
    task = _make_task(task_dir, gate=gate, rubric=_judged_rubric("clarity"))

    judge = StubJudge({"clarity": 0.9})
    result = FakeRunner().run_task(task, tmp_path / "scratch", judge=judge, fail_fast=False)

    # Gate still lost (the expected check failed)...
    assert result.passed is False
    # ...but full scoring graded the judge anyway.
    assert judge.calls == [("clarity", judge.calls[0][1], 1)]
    assert _check(result.report, "rubric").status == "run"


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_materialize_with_no_setup_dir_yields_empty_baseline(tmp_path: Path) -> None:
    """A task whose ``setup/`` is missing still produces a committed empty repo."""
    task_dir = tmp_path / "task"  # no setup/ created
    task_dir.mkdir()
    task = _make_task(task_dir, gate=_cc_gate())

    baseline = materialize(task, tmp_path / "scratch")
    assert baseline.commit
    assert baseline.setup_snapshot.is_dir()
    assert not any(baseline.setup_snapshot.iterdir())  # empty snapshot


def test_static_measurements_recurse_subdirs_and_skip_unparseable(tmp_path: Path) -> None:
    """Static metrics recurse into subpackages and skip files that don't parse."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, gate=_cc_gate())

    def _mutate(scratch: Path) -> None:
        pkg = scratch / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "deep.py").write_text(_REFACTORED, encoding="utf-8")  # nested, parses
        (scratch / "broken.py").write_text("def (:\n", encoding="utf-8")  # syntax error

    result = FakeRunner(_mutate).run_task(task, tmp_path / "scratch")
    keys = {d.scope_key for d in _scopes_for_evaluator(result.report, "cyclomatic_complexity")}
    assert any(k.startswith("pkg/deep.py") for k in keys)
    assert not any(k.startswith("broken.py") for k in keys)


def test_render_prompt_skips_non_matching_prompts() -> None:
    """Resolution scans every prompt md and returns only the id-matching one."""
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src" / "coding_agent_playbook"
    task_dir = src_root / "resources" / "eval_tasks" / "explain-pure-function"

    task = EvalTask(
        id="explain-pure-function",
        prompt_id="explain",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="coding_agent_playbook",
    )
    prompt = render_prompt(task)
    assert prompt
    assert "[prompt:explain]" not in prompt  # i.e. not the placeholder fallback
