"""End-to-end tests for the R1 eval runner + scoring bridge (hermetic).

Everything runs through :class:`~coding_agent_playbook.evals.fake_runner.FakeRunner`
so there is no network or agent CLI: a fixture lays down a ``setup/`` tree (a long
function + a passing test), then different fake mutations stand in for an agent's
edits and we assert the resulting :class:`EvaluationReport`.

The static-only tests are fast; the execution-non-regression tests actually run an
inner pytest (like ``tests/evaluators/test_execution_project.py``) and are marked
so they can be deselected in a fast loop.
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
from coding_agent_playbook.evaluators.types import AbsoluteThreshold, RegressionPolicy

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
    """A ``[metrics]`` policy that gates cyclomatic complexity on non-regression."""
    return MetricConfig(
        mode="regression",
        regression={"cyclomatic_complexity": RegressionPolicy(max_worsening=0.0)},
        thresholds={"cyclomatic_complexity": AbsoluteThreshold(warn=8.0, fail=15.0)},
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

    cc = [f for f in result.report.findings if f.evaluator == "cyclomatic_complexity"]
    classify = next(f for f in cc if f.scope_key.endswith("::classify"))
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
    cc = [f for f in result.report.findings if f.evaluator == "cyclomatic_complexity"]
    classify = next(f for f in cc if f.scope_key.endswith("::classify"))
    assert classify.level == "fail"
    assert classify.kind == "regression"
    assert classify.value > (classify.baseline or 0)


def test_absolute_mode_new_scope_uses_absolute_kind(tmp_path: Path) -> None:
    """A brand-new file (no baseline counterpart) grades absolute (kind=new)."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    # Threshold-only policy, absolute mode, on a fresh file the baseline lacks.
    metrics = MetricConfig(
        mode="absolute",
        thresholds={"cyclomatic_complexity": AbsoluteThreshold(warn=2.0, fail=4.0)},
    )
    task = _make_task(task_dir, metrics=metrics)

    runner = FakeRunner(write_files({"extra.py": _WORSE}))
    result = runner.run_task(task, tmp_path / "scratch")

    cc = [f for f in result.report.findings if f.scope_key.startswith("extra.py")]
    classify = next(f for f in cc if f.scope_key.endswith("::classify"))
    assert classify.kind == "new"
    assert classify.level == "fail"  # CC well over fail=4
    assert result.passed is False


# --------------------------------------------------------------------------- #
# [expected] BOOL findings
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


def test_expected_findings_pass_and_fail_merge_into_report(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, expected=_expected_all())

    # Agent: refactor mod.py (so it changes, contains _band) and add helper.py.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED, "helper.py": "x = 1\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    # R3: [expected] checks are now real BOOL evaluators named
    # ``expected:<kind>:<scope>`` whose finding scope_key is the same scope; index
    # by evaluator name (one evaluator per [expected] entry).
    by_name = {f.evaluator: f for f in result.report.findings}

    assert by_name["expected:file_exists:mod.py"].level == "ok"  # exists
    assert by_name["expected:file_exists:helper.py"].level == "ok"  # created

    contains = {
        name: f.level for name, f in by_name.items() if name.startswith("expected:file_contains:")
    }
    assert any(level == "ok" for name, level in contains.items() if "_band" in name)
    assert any(level == "fail" for name, level in contains.items() if "NOPE" in name)

    assert by_name["expected:file_unchanged:test_mod.py"].level == "ok"  # untouched
    assert by_name["expected:file_unchanged:mod.py"].level == "fail"  # rewritten by the refactor

    assert by_name["expected:file_forbidden:forbidden.py"].level == "ok"  # absent => good
    assert by_name["expected:file_forbidden:test_mod.py"].level == "fail"  # present => breach

    # Mixed pass/fail => report fails.
    assert result.passed is False


def test_expected_findings_come_from_unified_evaluators(tmp_path: Path) -> None:
    """R3: ``[expected]`` is no longer special-cased in scoring — the findings are
    real ``expected:*`` evaluator findings produced via ``evaluators_for_task`` +
    ``grade`` (BOOL, weight 0, so they gate but never feed the composite)."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, expected=_expected_all())

    runner = FakeRunner(write_files({"mod.py": _REFACTORED, "helper.py": "x = 1\n"}))
    result = runner.run_task(task, tmp_path / "scratch")

    expected = [f for f in result.report.findings if f.evaluator.startswith("expected:")]
    # One finding per [expected] entry (2 created + 2 contains + 2 unchanged + 2 forbidden).
    assert len(expected) == 8
    # They gate (a failure) but carry no composite weight (BOOL, default_weight 0).
    assert any(f.level == "fail" for f in expected)
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

    assert all(f.level != "fail" for f in result.report.findings)
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

    tpr = [f for f in result.report.findings if f.evaluator == "test_pass_rate"]
    assert tpr, "expected a test_pass_rate finding"
    assert all(f.level != "fail" for f in tpr)
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

    tpr = next(f for f in result.report.findings if f.evaluator == "test_pass_rate")
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


def test_scoring_skips_judged_evaluators_without_a_judge(tmp_path: Path) -> None:
    """The score() bridge must never produce judged findings (no ctx.judge)."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    # A rubric is present on the task, but R1 does not score it.
    from coding_agent_playbook.evals.task import Rubric

    task = _make_task(task_dir, metrics=_cc_metrics())
    task.rubric = Rubric(criteria=["clarity", "naming"])

    baseline = materialize(task, tmp_path / "scratch")
    write_files({"mod.py": _REFACTORED})(baseline.repo_root)
    candidate = capture(baseline.repo_root, baseline, "t")
    report = score(task, baseline, candidate)

    assert not any(f.evaluator.startswith("judged:") for f in report.findings)


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
# R2 — judged [rubric] scoring (hermetic via StubJudge)
# --------------------------------------------------------------------------- #


def test_judged_findings_appear_when_a_judge_is_passed(tmp_path: Path) -> None:
    """A [rubric] task run via FakeRunner + StubJudge surfaces judged findings."""
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

    judged = {f.scope_key: f for f in result.report.findings if f.evaluator.startswith("judged:")}
    by_eval = {f.evaluator for f in result.report.findings if f.evaluator.startswith("judged:")}
    assert by_eval == {"judged:clarity", "judged:naming"}
    # SCORE findings carry the stub scores.
    clarity = next(f for f in result.report.findings if f.evaluator == "judged:clarity")
    assert clarity.value == pytest.approx(0.9)
    assert clarity.scope_key == "rubric"
    assert judged  # keyed on the rubric label


def test_judged_findings_contribute_to_the_composite(tmp_path: Path) -> None:
    """Judged criteria feed the weighted composite (default_weight > 0)."""
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


def test_low_judged_score_fails_gate_with_min_score(tmp_path: Path) -> None:
    """A min-score ``fail`` threshold (keyed on the judged name) gates a low score."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    # Absolute-mode policy with a hard floor on the judged criterion: fail<0.6.
    metrics = MetricConfig(
        mode="absolute",
        thresholds={"judged:clarity": AbsoluteThreshold(fail=0.6)},
    )
    task = _make_task(task_dir, metrics=metrics)
    task.rubric = Rubric(criteria=["clarity"])

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.3}))

    clarity = next(f for f in result.report.findings if f.evaluator == "judged:clarity")
    assert clarity.level == "fail"
    assert result.passed is False


def test_high_judged_score_passes_gate_with_min_score(tmp_path: Path) -> None:
    """The same min-score floor passes when the judged score clears it."""
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    metrics = MetricConfig(
        mode="absolute",
        thresholds={"judged:clarity": AbsoluteThreshold(fail=0.6)},
    )
    task = _make_task(task_dir, metrics=metrics)
    task.rubric = Rubric(criteria=["clarity"])

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_task(task, tmp_path / "scratch", judge=StubJudge({"clarity": 0.95}))

    clarity = next(f for f in result.report.findings if f.evaluator == "judged:clarity")
    assert clarity.level == "ok"
    assert result.passed is True


def test_no_judge_preserves_deterministic_only_r1_behaviour(tmp_path: Path) -> None:
    """With no judge, judged findings are absent and the report is R1-identical."""
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())
    task.rubric = Rubric(criteria=["clarity", "naming"])

    # No judge argument => deterministic-only.
    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_task(task, tmp_path / "scratch")

    assert not any(f.evaluator.startswith("judged:") for f in result.report.findings)
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
    """Static evaluators recurse into subpackages and skip files that don't parse."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, metrics=_cc_metrics())

    def _mutate(scratch: Path) -> None:
        pkg = scratch / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "deep.py").write_text(_REFACTORED, encoding="utf-8")  # nested, parses
        (scratch / "broken.py").write_text("def (:\n", encoding="utf-8")  # syntax error

    result = FakeRunner(_mutate).run_task(task, tmp_path / "scratch")
    keys = {f.scope_key for f in result.report.findings if f.evaluator == "cyclomatic_complexity"}
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
