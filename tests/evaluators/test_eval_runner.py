"""End-to-end tests for the eval runner + scoring bridge (hermetic, T5a).

Everything runs through :class:`~coding_agent_playbook.evals.fake_runner.FakeRunner`
so there is no network or agent CLI: a fixture lays down a ``setup/`` tree (a long
function + a passing test), then different fake mutations stand in for an agent's
edits and we assert the resulting :class:`EvaluationReport`.

T5a cuts ``score()`` over from the old ``grade(..., extra_evaluators=…)`` path to
the :class:`~coding_agent_playbook.evaluators.rubric.Rubric` returned by
:func:`~coding_agent_playbook.evals.task.rubric_for_task`. The report now carries
:attr:`EvaluationReport.checks` — one
:class:`~coding_agent_playbook.evaluators.types.CheckResult` per compiled check,
each with its per-scope :class:`~coding_agent_playbook.evaluators.types.ScopeDetail`
``subresults``. Tests assert through ``report.checks`` (the new shape) rather than
the flat ``report.findings`` list. Gate verdicts and which checks fail are
identical to the pre-cutover behaviour.

The static-only tests are fast; the execution-non-regression tests actually run an
inner pytest and are slower.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

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
from coding_agent_playbook.evals.task import (
    EvalTask,
    ExpectedOutcome,
    TaskInvocation,
)
from coding_agent_playbook.evaluators import EvaluationReport, MetricConfig
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    CheckResult,
    RegressionPolicy,
    ScopeDetail,
)

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

# A refactor that *lowers* CC of ``classify`` by extracting the band lookup into a
# small helper — the public function keeps the same behaviour but fewer branches.
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
# Report helpers — walk the new report.checks → subresults shape
# --------------------------------------------------------------------------- #


def _scope_details(report: EvaluationReport) -> list[ScopeDetail]:
    """Every per-scope :class:`ScopeDetail` leaf across the run checks."""
    out: list[ScopeDetail] = []
    for check in report.checks:
        if check.status != "run":
            continue
        out.extend(sub for sub in check.subresults if isinstance(sub, ScopeDetail))
    return out


def _scopes_for_evaluator(report: EvaluationReport, evaluator: str) -> list[ScopeDetail]:
    """Leaves whose ``evaluator`` matches (the metric name / check id)."""
    return [d for d in _scope_details(report) if d.evaluator == evaluator]


def _check(report: EvaluationReport, check_id: str) -> CheckResult:
    """The single run :class:`CheckResult` with ``check_id`` (raises if absent)."""
    return next(c for c in report.checks if c.check_id == check_id)


def _make_setup(task_dir: Path, *, mod_source: str = _LONG_FN, test_source: str = _TEST_OK) -> None:
    """Lay down ``<task_dir>/setup/{mod.py,test_mod.py}``."""
    setup = task_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text(mod_source, encoding="utf-8")
    (setup / "test_mod.py").write_text(test_source, encoding="utf-8")


def _make_task(
    task_dir: Path,
    *,
    metrics: MetricConfig | None = None,
    expected: ExpectedOutcome | None = None,
    invocation: TaskInvocation | None = None,
    prompt_id: str = "refactor",
) -> EvalTask:
    return EvalTask(
        id="t-fixture",
        prompt_id=prompt_id,
        description="fixture task",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        metrics=metrics,
        expected=expected,
        invocation=invocation or TaskInvocation(),
    )


def _cc_metrics() -> MetricConfig:
    """A ``[metrics]`` policy that gates cyclomatic complexity on non-regression.

    The thresholds are ``0-1`` cutoffs on the normalized CC score
    (``RampNormalizer(good=5, bad=20)``); a *new* scope (no baseline) falls back
    to these absolute bounds, and the refactor's new ``_band`` (CC 3 -> score 1.0)
    clears ``warn=0.5`` so the good refactor still passes.
    """
    return MetricConfig(
        mode="regression",
        regression={"cyclomatic_complexity": RegressionPolicy(max_worsening=0.0)},
        thresholds={"cyclomatic_complexity": AbsoluteThreshold(warn=0.5, fail=0.25)},
    )


# --------------------------------------------------------------------------- #
# Orchestration helpers
# --------------------------------------------------------------------------- #


def test_materialize_copies_setup_and_commits_baseline(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    scratch = tmp_path / "scratch"

    baseline = materialize(task, scratch)

    assert (scratch / "mod.py").is_file()
    assert (scratch / ".git").is_dir()
    assert baseline.commit  # a real SHA
    # The pristine snapshot is a separate tree the agent cannot reach.
    assert baseline.setup_snapshot != scratch
    assert (baseline.setup_snapshot / "mod.py").read_text() == _LONG_FN


def test_capture_includes_new_files_in_diff_and_changed(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
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
        invocation=TaskInvocation(prompt_args="do the thing"),
        prompt_id="nonexistent",
    )
    prompt = render_prompt(task)
    assert "nonexistent" in prompt
    assert "do the thing" in prompt


def test_render_prompt_resolves_a_real_shipped_prompt() -> None:
    """A task pointing at a shipped prompt renders that prompt's real body.

    Resolution reads ``resources/prompts/`` directly (no SyncContext/config), so
    it works for the engine's own resources, which carry no
    ``.coding-agent-playbook.toml``.
    """
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
    # The refactor prompt's distinctive prose + the appended args.
    assert "refactoring existing code" in prompt
    assert "extract the totals block" in prompt


# --------------------------------------------------------------------------- #
# FakeRunner round-trips (static, fast)
# --------------------------------------------------------------------------- #


def test_good_refactor_passes_and_cc_drops(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch")

    assert isinstance(result.report, EvaluationReport)
    assert result.passed is True
    assert result.harness == "fake"
    assert result.task_id == "t-fixture"

    # The CC metric compiled to a non-regression check; its scope leaves carry
    # the per-function complexity.
    cc_check = _check(result.report, "nonreg:cyclomatic_complexity")
    assert cc_check.passed is True
    classify = next(
        sub
        for sub in cc_check.subresults
        if isinstance(sub, ScopeDetail) and sub.scope_key.endswith("::classify")
    )
    # CC of classify dropped vs the baseline (non-regression improvement).
    assert classify.baseline is not None
    assert classify.value < classify.baseline
    assert classify.level == "ok"


def test_worsening_refactor_fails_with_regression_finding(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())

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
    # Threshold-only policy, absolute mode, on a fresh file the baseline lacks.
    # 0-1 cutoffs: _WORSE's classify is CC 11 -> normalized score 0.6, which is
    # below fail=0.7, so the new scope fails the absolute gate.
    metrics = MetricConfig(
        mode="absolute",
        thresholds={"cyclomatic_complexity": AbsoluteThreshold(warn=0.9, fail=0.7)},
    )
    task = _make_task(task_dir, metrics=metrics)

    runner = FakeRunner(write_files({"extra.py": _WORSE}))
    result = runner.run_task(task, tmp_path / "scratch")

    # absolute mode compiles to a ThresholdCheck.
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
# [expected] file checks
# --------------------------------------------------------------------------- #


def _expected_all() -> ExpectedOutcome:
    return ExpectedOutcome(
        files_created=["mod.py", "helper.py"],
        files_must_contain=[
            {"path": "mod.py", "pattern": r"def _band"},
            {"path": "mod.py", "pattern": r"NOPE_not_present"},
        ],
        files_unchanged=["test_mod.py", "mod.py"],
        files_forbidden=["forbidden.py", "test_mod.py"],
    )


def test_expected_checks_pass_and_fail_merge_into_report(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, expected=_expected_all())

    # Agent: refactor mod.py (so it changes, contains _band) and add helper.py.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED, "helper.py": "x = 1\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    # Each [expected] entry is its own Check, keyed by a stable check id.
    by_id = {c.check_id: c for c in result.report.checks}

    assert by_id["file_exists:mod.py"].passed is True  # exists
    assert by_id["file_exists:helper.py"].passed is True  # created

    contains = {cid: c.passed for cid, c in by_id.items() if cid.startswith("file_contains:")}
    assert any(passed for cid, passed in contains.items() if "_band" in cid)
    assert any(not passed for cid, passed in contains.items() if "NOPE" in cid)

    assert by_id["file_unchanged:test_mod.py"].passed is True  # untouched
    assert by_id["file_unchanged:mod.py"].passed is False  # rewritten by the refactor

    assert by_id["file_forbidden:forbidden.py"].passed is True  # absent => good
    assert by_id["file_forbidden:test_mod.py"].passed is False  # present => breach

    # Mixed pass/fail => report fails.
    assert result.passed is False


def test_expected_checks_come_from_the_rubric(tmp_path: Path) -> None:
    """[expected] is compiled into deterministic file Checks via ``rubric_for_task``;
    each is a pure gate (weight 0, so it gates but never feeds the composite)."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, expected=_expected_all())

    runner = FakeRunner(write_files({"mod.py": _REFACTORED, "helper.py": "x = 1\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    file_checks = [
        c
        for c in result.report.checks
        if c.status == "run"
        and (
            c.check_id.startswith("file_exists:")
            or c.check_id.startswith("file_contains:")
            or c.check_id.startswith("file_unchanged:")
            or c.check_id.startswith("file_forbidden:")
        )
    ]
    # One check per [expected] entry (2 created + 2 contains + 2 unchanged + 2 forbidden).
    assert len(file_checks) == 8
    # They gate (a failure) but carry no composite weight (weight 0).
    assert any(not c.passed for c in file_checks)
    assert all(c.weight == 0.0 for c in file_checks)
    assert result.report.composite is None


def test_expected_all_passing_yields_a_passing_report(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    expected = ExpectedOutcome(
        files_created=["helper.py"],
        files_must_contain=[{"path": "helper.py", "pattern": r"answer = 42"}],
        files_unchanged=["test_mod.py", "mod.py"],
        files_forbidden=["nope.py"],
    )
    task = _make_task(task_dir, expected=expected)

    runner = FakeRunner(write_files({"helper.py": "answer = 42\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    assert all(c.passed for c in result.report.checks if c.status == "run")
    assert result.passed is True


# --------------------------------------------------------------------------- #
# Execution non-regression (runs an inner pytest)
# --------------------------------------------------------------------------- #


def _exec_metrics() -> MetricConfig:
    return MetricConfig(
        mode="regression",
        run_tests=True,
        regression={
            "test_pass_rate": RegressionPolicy(max_worsening=0.0),
            "coverage": RegressionPolicy(max_worsening=0.0),
        },
    )


def test_execution_non_regression_passes_when_tests_stay_green(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_exec_metrics())

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
    task = _make_task(task_dir, metrics=_exec_metrics())

    # Break behaviour: classify(5) now returns "WRONG", so the test fails.
    broken = textwrap.dedent(
        """\
        def classify(n):
            return "WRONG"
        """
    )
    runner = FakeRunner(write_files({"mod.py": broken}))
    result = runner.run_task(task, tmp_path / "scratch")

    tpr = next(d for d in _scope_details(result.report) if d.evaluator == "test_pass_rate")
    # Baseline had a passing suite (rate 1.0); candidate drops below => regression.
    assert tpr.baseline == pytest.approx(1.0)
    assert tpr.value < 1.0
    assert tpr.level == "fail"
    assert result.passed is False


# --------------------------------------------------------------------------- #
# Result model + no-judge invariant
# --------------------------------------------------------------------------- #


def test_run_task_with_no_blocks_passes_trivially(tmp_path: Path) -> None:
    """A task with no [metrics] and no [expected] still produces a passing report."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)

    result = FakeRunner().run_task(task, tmp_path / "scratch")
    assert isinstance(result.report, EvaluationReport)
    assert result.passed is True
    assert result.report.composite is None
    assert result.aggregate_score == 1.0
    # No checks compiled from an empty task.
    assert result.report.checks == []


def test_scoring_skips_judged_checks_without_a_judge(tmp_path: Path) -> None:
    """The score() bridge must never grade judged checks (no ctx.judge)."""
    task_dir = tmp_path / "task"
    # A rubric is present on the task, but with no judge it does not score.
    from coding_agent_playbook.evals.task import Rubric

    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())
    task.rubric = Rubric(criteria=["clarity", "naming"])

    baseline = materialize(task, tmp_path / "scratch")
    write_files({"mod.py": _REFACTORED})(baseline.repo_root)
    candidate = capture(baseline.repo_root, baseline, "t")
    report = score(task, baseline, candidate)

    # The judged checks are present but skipped (never produced a run finding).
    judge_checks = [c for c in report.checks if c.check_id.startswith("judge:")]
    assert judge_checks  # they were compiled
    assert all(c.status == "skipped" for c in judge_checks)
    assert not any(d.evaluator.startswith("judge:") for d in _scope_details(report))


def test_score_is_callable_directly_with_handles(tmp_path: Path) -> None:
    """``score(task, baseline, candidate)`` works without going through run_task."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())

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


def test_judged_checks_appear_when_a_judge_is_passed(tmp_path: Path) -> None:
    """A [rubric] task run via FakeRunner + StubJudge surfaces judged scope leaves."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    task.rubric = Rubric(criteria=["clarity", "naming"])

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(
        task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.9, "naming": 0.7})
    )

    judge_ids = {c.check_id for c in result.report.checks if c.check_id.startswith("judge:")}
    assert judge_ids == {"judge:clarity", "judge:naming"}
    # The clarity check ran and carries the stub score on its scope leaf.
    clarity = _check(result.report, "judge:clarity")
    assert clarity.status == "run"
    leaf = clarity.subresults[0]
    assert isinstance(leaf, ScopeDetail)
    assert leaf.value == pytest.approx(0.9)
    assert leaf.scope_key == "rubric"


def test_judged_checks_contribute_to_the_composite(tmp_path: Path) -> None:
    """Judged criteria feed the weighted composite (weight > 0)."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    # Uniform weights (0.5 each); scores 1.0 and 0.0 => composite 0.5.
    task.rubric = Rubric(criteria=["good", "bad"])

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch", judge=StubJudge({"good": 1.0, "bad": 0.0}))

    assert result.report.composite == pytest.approx(0.5)
    assert result.aggregate_score == pytest.approx(0.5)


def test_low_judged_score_does_not_gate_but_lands_a_fail_leaf(tmp_path: Path) -> None:
    """A judged score below the check threshold fails the leaf but does not gate.

    ``JudgeCheck`` is ``required=False`` (judged criteria score the composite, not
    the gate), so a low score yields a failing leaf without sinking ``passed``.
    """
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    task.rubric = Rubric(criteria=["clarity"])

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    # threshold defaults to 0.5; 0.3 < 0.5 => the leaf fails.
    result = runner.run_task(task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.3}))

    clarity = _check(result.report, "judge:clarity")
    assert clarity.passed is False
    leaf = clarity.subresults[0]
    assert isinstance(leaf, ScopeDetail)
    assert leaf.level == "fail"
    # required=False => the failing judged leaf does not gate.
    assert result.passed is True


def test_high_judged_score_passes_its_check(tmp_path: Path) -> None:
    """A judged score clearing the threshold passes the check's leaf."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    task.rubric = Rubric(criteria=["clarity"])

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.95}))

    clarity = _check(result.report, "judge:clarity")
    assert clarity.passed is True
    leaf = clarity.subresults[0]
    assert isinstance(leaf, ScopeDetail)
    assert leaf.level == "ok"
    assert result.passed is True


def test_no_judge_preserves_deterministic_only_behaviour(tmp_path: Path) -> None:
    """With no judge, judged checks skip and the deterministic report is unchanged."""
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())
    task.rubric = Rubric(criteria=["clarity", "naming"])

    # No judge argument => deterministic-only.
    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(task, tmp_path / "scratch")

    judge_checks = [c for c in result.report.checks if c.check_id.startswith("judge:")]
    assert all(c.status == "skipped" for c in judge_checks)
    assert not any(d.evaluator.startswith("judge:") for d in _scope_details(result.report))
    assert result.passed is True


def test_samples_threaded_through_to_the_judge(tmp_path: Path) -> None:
    """``run_task(samples=N)`` reaches the judge as the per-criterion ``n``."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    task.rubric = Rubric(criteria=["clarity"])

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(
        task, tmp_path / "scratch", judge=judge, samples=5
    )
    assert judge.calls == [("clarity", judge.calls[0][1], 5)]


def test_judge_artifact_is_the_candidate_diff(tmp_path: Path) -> None:
    """The judged artifact is the candidate's captured git diff (the agent's change)."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir)
    task.rubric = Rubric(criteria=["clarity"])

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(write_files({"helper.py": "answer = 42\n"})).run_task(
        task, tmp_path / "scratch", judge=judge
    )
    _criterion, artifact, _n = judge.calls[0]
    # The diff contains the newly-created file's contents.
    assert "answer = 42" in str(artifact)


# --------------------------------------------------------------------------- #
# Fail-fast: a lost deterministic gate skips the judge tier
# --------------------------------------------------------------------------- #


def test_fail_fast_skips_the_judge_when_an_expected_check_fails(tmp_path: Path) -> None:
    """fail_fast (the runner default) skips the judge tier once the gate is lost.

    A failing required ``[expected]`` check (DETERMINISTIC tier) settles the gate,
    so the cost-tiered scheduler short-circuits the JUDGED tier — the judge's
    ``score_criterion`` is never called (no LLM call wasted).
    """
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    # An [expected] check the no-op agent will violate (the file is never created).
    expected = ExpectedOutcome(files_created=["never_created.py"])
    task = _make_task(task_dir, expected=expected)
    task.rubric = Rubric(criteria=["clarity"])

    judge = StubJudge({"clarity": 0.9})
    # FakeRunner's default no-op mutation: never creates never_created.py.
    result = FakeRunner().run_task(task, tmp_path / "scratch", judge=judge)

    assert result.passed is False
    # The judge was never invoked.
    assert judge.calls == []
    # And its check is recorded skipped, not run.
    clarity = _check(result.report, "judge:clarity")
    assert clarity.status == "skipped"


def test_full_scoring_runs_the_judge_even_after_a_failed_gate(tmp_path: Path) -> None:
    """fail_fast=False (``--full-scoring``) grades the judge tier regardless."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    expected = ExpectedOutcome(files_created=["never_created.py"])
    task = _make_task(task_dir, expected=expected)
    task.rubric = Rubric(criteria=["clarity"])

    judge = StubJudge({"clarity": 0.9})
    result = FakeRunner().run_task(task, tmp_path / "scratch", judge=judge, fail_fast=False)

    # Gate still lost (the expected check failed)...
    assert result.passed is False
    # ...but full scoring graded the judge anyway.
    assert judge.calls == [("clarity", judge.calls[0][1], 1)]
    clarity = _check(result.report, "judge:clarity")
    assert clarity.status == "run"
    leaf = clarity.subresults[0]
    assert isinstance(leaf, ScopeDetail)
    assert leaf.value == pytest.approx(0.9)


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_materialize_with_no_setup_dir_yields_empty_baseline(tmp_path: Path) -> None:
    """A task whose ``setup/`` is missing still produces a committed empty repo."""
    task_dir = tmp_path / "task"  # no setup/ created
    task_dir.mkdir()
    task = _make_task(task_dir)

    baseline = materialize(task, tmp_path / "scratch")
    assert baseline.commit
    assert baseline.setup_snapshot.is_dir()
    assert not any(baseline.setup_snapshot.iterdir())  # empty snapshot


def test_static_measurements_recurse_subdirs_and_skip_unparseable(tmp_path: Path) -> None:
    """Static metrics recurse into subpackages and skip files that don't parse."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())

    def _mutate(scratch: Path) -> None:
        pkg = scratch / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "deep.py").write_text(_REFACTORED, encoding="utf-8")  # nested, parses
        (scratch / "broken.py").write_text("def (:\n", encoding="utf-8")  # syntax error

    result = FakeRunner(_mutate).run_task(task, tmp_path / "scratch")
    keys = {d.scope_key for d in _scopes_for_evaluator(result.report, "cyclomatic_complexity")}
    # The nested file was measured...
    assert any(k.startswith("pkg/deep.py") for k in keys)
    # ...and the unparseable file produced no findings (skipped, not crashed).
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
    # The explain prompt resolved (not the refactor/review/etc. siblings).
    assert prompt
    assert "[prompt:explain]" not in prompt  # i.e. not the placeholder fallback
