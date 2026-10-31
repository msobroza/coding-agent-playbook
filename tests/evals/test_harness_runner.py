"""End-to-end tests for the eval runner + scoring bridge (hermetic, C7).

Everything runs through :class:`~coding_agent_playbook.evals.run.fake_runner.FakeRunner`
so there is no network or agent CLI: a fixture lays down a ``setup/`` tree (a long
function + a passing test), then different fake mutations stand in for an agent's
edits and we assert the resulting :class:`EvaluationReport`.

C7 sources the checks from the **C6 compiler**: a sample's ``[gate]``/``[rubric]``
blocks compile into one per-trial
:class:`~coding_agent_playbook.grading.rubric.Rubric` carrying the two named
layer checks (``id="gate"`` / ``id="rubric"``); the per-trial **verdict** is then
derived from the layer results (skipped-neutral) onto ``report.passed``. Metric
gates (CC, coverage, test_pass_rate) enter via ``threshold``/``non_regression``
*checks* inside the gate bind; the deterministic file predicates are the
``file_*`` checks; the judged criteria live in a ``rubric`` group inside the
``[rubric]`` bind.

These tests build the new-schema sample dicts directly. The static-only tests are
fast; the execution-non-regression tests actually run an inner pytest and are
slower.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.report_format import (
    format_sample_result_text,
    sample_result_to_dict,
)
from coding_agent_playbook.evals.run.fake_runner import FakeRunner, write_files
from coding_agent_playbook.evals.run.harness_runner import (
    TIMED_OUT_RETURNCODE,
    AgentRun,
    Baseline,
    Candidate,
    SampleResult,
    capture,
    materialize,
    timed_out_run,
)
from coding_agent_playbook.evals.run.scoring import (
    BaselineSuiteError,
    SuiteToolchainError,
    _suite_env,
    score,
)
from coding_agent_playbook.evals.sample import EvalSample, SampleInvocation
from coding_agent_playbook.grading.types import CheckResult, EvaluationReport, ScopeDetail
from tests._catalog import CORE_ROOT

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
# Setup / sample fixtures (new C7 schema)
# --------------------------------------------------------------------------- #


def _make_setup(
    sample_dir: Path, *, mod_source: str = _LONG_FN, test_source: str = _TEST_OK
) -> None:
    """Lay down ``<sample_dir>/setup/{mod.py,test_mod.py}``."""
    setup = sample_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text(mod_source, encoding="utf-8")
    (setup / "test_mod.py").write_text(test_source, encoding="utf-8")


def _make_sample(
    sample_dir: Path,
    *,
    gate: dict[str, Any] | None = None,
    rubric: dict[str, Any] | None = None,
    verdict: str | None = None,
    verdict_block: dict[str, Any] | None = None,
    invocation: SampleInvocation | None = None,
    prompt_id: str = "refactor",
) -> EvalSample:
    """Build an :class:`EvalSample` from the new-schema ``[gate]``/``[rubric]`` dicts.

    ``verdict`` defaults sensibly: ``"gate and rubric"`` when both blocks are
    present, ``"gate"`` for gate-only, ``"rubric"`` for rubric-only. To author
    the weighted form (C10) pass ``verdict_block`` (the raw ``[verdict]`` dict)
    instead — mutually exclusive with ``verdict``.
    """
    data: dict[str, Any] = {
        "id": "t-fixture",
        "description": "fixture sample",
    }
    if gate is not None:
        data["gate"] = gate
    if rubric is not None:
        data["rubric"] = rubric
    if verdict_block is not None:
        assert verdict is None, "pass either `verdict` (boolean) or `verdict_block` (raw)"
        data["verdict"] = verdict_block
    else:
        if verdict is None:
            if gate is not None and rubric is not None:
                verdict = "gate and rubric"
            elif gate is not None:
                verdict = "gate"
            else:
                verdict = "rubric"
        data["verdict"] = {"trial": verdict}
    sample = EvalSample.from_dict(
        data, prompt_id=prompt_id, source_path=sample_dir / "sample.toml", source_package="<test>"
    )
    if invocation is not None:
        sample.invocation = invocation
    return sample


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
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())
    scratch = tmp_path / "scratch"

    baseline = materialize(sample, scratch)

    assert (scratch / "mod.py").is_file()
    assert (scratch / ".git").is_dir()
    assert baseline.commit  # a real SHA
    assert baseline.setup_snapshot != scratch
    assert (baseline.setup_snapshot / "mod.py").read_text() == _LONG_FN


def test_capture_includes_new_files_in_diff_and_changed(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())
    scratch = tmp_path / "scratch"
    baseline = materialize(sample, scratch)

    (scratch / "new.py").write_text("x = 1\n", encoding="utf-8")
    candidate = capture(scratch, baseline, "transcript-here")

    assert "new.py" in candidate.changed_files
    assert "new.py" in candidate.diff
    assert candidate.transcript == "transcript-here"


def test_render_prompt_falls_back_for_unresolvable_prompt(tmp_path: Path) -> None:
    """A synthetic sample outside any ``eval_samples/`` layer resolves to a placeholder."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(
        sample_dir,
        gate=_cc_gate(),
        invocation=SampleInvocation(prompt_args="do the thing"),
        prompt_id="nonexistent",
    )
    prompt = render_prompt(sample)
    assert "nonexistent" in prompt
    assert "do the thing" in prompt


@pytest.mark.catalog
def test_render_prompt_resolves_a_real_shipped_prompt() -> None:
    """A sample pointing at a shipped (non-templated) prompt renders its real body."""
    sample_dir = CORE_ROOT / "eval_samples" / "refactor" / "extract-helper"
    assert (sample_dir / "sample.toml").is_file()

    sample = EvalSample(
        id="refactor-extract-helper",
        prompt_id="refactor",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="coding_agent_playbook",
        invocation=SampleInvocation(prompt_args="extract the totals block"),
    )
    prompt = render_prompt(sample)
    assert "refactoring existing code" in prompt
    assert "extract the totals block" in prompt


# --------------------------------------------------------------------------- #
# FakeRunner round-trips (static metric gate, fast)
# --------------------------------------------------------------------------- #


def test_good_refactor_passes_and_cc_drops(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_sample(sample, tmp_path / "scratch")

    assert isinstance(result.report, EvaluationReport)
    assert result.passed is True
    assert result.harness == "fake"
    assert result.sample_id == "t-fixture"

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
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())

    runner = FakeRunner(write_files({"mod.py": _WORSE}))
    result = runner.run_sample(sample, tmp_path / "scratch")

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
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
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
    sample = _make_sample(sample_dir, gate=gate)

    runner = FakeRunner(write_files({"extra.py": _WORSE}))
    result = runner.run_sample(sample, tmp_path / "scratch")

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
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_file_gate())

    # Agent: refactor mod.py (so it changes + contains _band) and add helper.py.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED, "helper.py": "x = 1\n"}))
    result = runner.run_sample(sample, tmp_path / "scratch")

    by_id = _checks_by_id(result.report)
    assert by_id["file_exists:mod.py"].passed is True  # exists
    assert by_id["file_exists:helper.py"].passed is True  # created
    assert by_id["file_contains:mod.py~/def _band/"].passed is True  # contains _band
    assert by_id["file_unchanged:mod.py"].passed is False  # rewritten by the refactor
    assert by_id["file_forbidden:test_mod.py"].passed is False  # present => breach

    # The gate ANDs them, so a single breach fails the gate (and the verdict).
    assert result.passed is False


def test_gate_all_passing_yields_a_passing_report(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {
        "expr": "helper_exists and answer and src_unchanged and no_nope",
        "bind": {
            "helper_exists": {"check": "file_exists", "path": "helper.py"},
            "answer": {"check": "file_contains", "path": "helper.py", "pattern": r"answer = 42"},
            "src_unchanged": {"check": "file_unchanged", "path": "mod.py"},
            "no_nope": {"check": "file_forbidden", "path": "nope.py"},
        },
    }
    sample = _make_sample(sample_dir, gate=gate)

    runner = FakeRunner(write_files({"helper.py": "answer = 42\n"}))
    result = runner.run_sample(sample, tmp_path / "scratch")

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
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_exec_gate())

    # A behaviour-preserving refactor: tests still pass.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_sample(sample, tmp_path / "scratch")

    tpr = _scopes_for_evaluator(result.report, "test_pass_rate")
    assert tpr, "expected a test_pass_rate scope leaf"
    assert all(d.level != "fail" for d in tpr)
    assert result.passed is True


def test_execution_non_regression_fails_when_a_test_breaks(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_exec_gate())

    broken = textwrap.dedent(
        """\
        def classify(n):
            return "WRONG"
        """
    )
    runner = FakeRunner(write_files({"mod.py": broken}))
    result = runner.run_sample(sample, tmp_path / "scratch")

    tpr = next(d for d in _scope_details(result.report) if d.evaluator == "test_pass_rate")
    assert tpr.baseline == pytest.approx(1.0)
    assert tpr.value < 1.0
    assert tpr.level == "fail"
    assert result.passed is False


def _suite_green_gate() -> dict[str, Any]:
    """The shipped samples' ``suite_green`` gate: every test passes (``tests_pass``)."""
    return {"expr": "suite_green", "bind": {"suite_green": {"check": "tests_pass"}}}


def _run_suite_green(
    tmp_path: Path, files: dict[str, str], gate: dict[str, Any] | None = None
) -> SampleResult:
    """Run the ``suite_green`` sample (or ``gate``) with an agent that writes ``files``."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=gate or _suite_green_gate())
    return FakeRunner(write_files(files)).run_sample(sample, tmp_path / "scratch")


def test_a_scoring_suite_that_hangs_is_stopped_and_fails_tests_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: the scoring pytest ran with no timeout, so an agent's endless test stalled a run.

    A bound alone was not enough: scoring swallowed the timeout's ``RuntimeError``,
    and ``tests_pass`` over no measurement passes vacuously.
    """

    candidate_tree = tmp_path / "scratch"

    class _HangingPytest(subprocess.Popen[str]):
        """The candidate's pytest never finishes within a bound; an unbounded wait lets it."""

        def __init__(self, args: Any, **kwargs: Any) -> None:
            self.hangs = args[1:3] == ["-m", "pytest"] and kwargs.get("cwd") == candidate_tree
            super().__init__(args, **kwargs)

        def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[Any, Any]:
            if self.hangs and timeout is not None:
                raise subprocess.TimeoutExpired(self.args, timeout)
            return super().communicate(input, timeout)

    monkeypatch.setattr(
        "coding_agent_playbook.grading.execution_metrics.project.subprocess.Popen", _HangingPytest
    )
    result = _run_suite_green(tmp_path, {"mod.py": _REFACTORED})

    check = _check(result.report, "threshold:test_pass_rate")
    assert check.passed is False
    assert check.detail == "the test suite gave no result: it timed out after 300 s"
    assert result.passed is False
    assert "it timed out after 300 s" in format_sample_result_text(result)
    gate = sample_result_to_dict(result)["report"]["checks"][0]  # type: ignore[index]
    assert gate["details"] == [f"threshold:test_pass_rate: {check.detail}"]


@pytest.mark.parametrize(
    ("conftest", "reason"),
    [
        ('raise RuntimeError("boom")\n', "it exited 4 with no junit report"),
        ("import os\nos._exit(0)\n", "it exited 0 with no junit report"),
    ],
    ids=["conftest-raises", "conftest-exits-0"],
)
def test_a_scoring_suite_that_leaves_no_report_fails_tests_pass(
    tmp_path: Path, conftest: str, reason: str
) -> None:
    """Regression: a suite that wrote no junit report passed ``tests_pass`` with no measurement.

    A raising ``conftest.py`` makes pytest exit 4 and scoring swallowed the error;
    an ``os._exit(0)`` exits 0, which read as an empty, all-passing report.
    """
    result = _run_suite_green(tmp_path, {"conftest.py": conftest})

    check = _check(result.report, "threshold:test_pass_rate")
    assert (check.passed, check.detail) == (False, f"the test suite gave no result: {reason}")
    assert result.passed is False


def test_every_execution_check_fails_over_a_suite_with_no_result(tmp_path: Path) -> None:
    """Regression: a coverage check over a suite with no result graded zero scopes and passed."""
    result = _run_suite_green(tmp_path, {"conftest.py": "import os\nos._exit(0)\n"}, _exec_gate())

    for check_id in ("nonreg:test_pass_rate", "nonreg:coverage"):
        assert _check(result.report, check_id).passed is False, check_id
    assert result.passed is False


def test_an_inherited_pytest_addopts_cannot_deselect_the_failing_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: ``-o addopts=`` leaves ``PYTEST_ADDOPTS``, so a caller's ``-k`` hid failures."""
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing_matches")
    broken = 'def classify(n):\n    return "WRONG"\n'

    result = _run_suite_green(tmp_path, {"mod.py": broken})

    assert _check(result.report, "threshold:test_pass_rate").passed is False
    assert result.passed is False


_SECRET_NAMES = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "PLAYBOOK_PROBE_TOKEN", "SSH_AUTH_SOCK")


def test_the_scoring_suite_does_not_inherit_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: agent code in the scoring suite read the engine's API keys, tokens and agent socket."""
    for name in _SECRET_NAMES:
        monkeypatch.setenv(name, "leaked")
    probe = (
        "import os\n\n\ndef test_env():\n"
        f"    assert not [n for n in {_SECRET_NAMES!r} if n in os.environ]\n"
        "    assert os.environ.get('PATH')\n"
    )

    result = _run_suite_green(tmp_path, {"mod.py": _REFACTORED, "test_env.py": probe})

    assert _check(result.report, "threshold:test_pass_rate").passed is True
    assert result.passed is True


def test_the_suite_env_keeps_only_the_allowlist_and_sets_the_coverage_file() -> None:
    """Only the allowlisted names and the ``LC_`` locale reach the suite, Windows case included."""
    kept = {"PATH": "/bin", "HOME": "/h", "TMPDIR": "/t", "LC_ALL": "C", "PYTHONPATH": "/p"}
    kept |= {"SystemRoot": "C:\\Windows"}
    dropped = ["ANTHROPIC_API_KEY", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "PYTEST_ADDOPTS"]
    dropped += ["COVERAGE_PROCESS_START", "COV_CORE_SOURCE"]

    env = _suite_env(Path("/r"), {**kept, **dict.fromkeys(dropped, "x")})

    assert env == {**kept, "COVERAGE_FILE": str(Path("/r") / ".coverage")}


def test_a_scoring_suite_that_cannot_start_stops_the_sample(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: scoring swallowed a launch failure, and every execution check passed on no rows."""

    def _no_program(argv: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    monkeypatch.setattr(
        "coding_agent_playbook.grading.execution_metrics.project._run_in_session", _no_program
    )

    with pytest.raises(RuntimeError, match=r"could not run the test command"):
        _run_suite_green(tmp_path, {"mod.py": _REFACTORED})


def test_a_baseline_suite_with_no_result_makes_the_sample_unscorable(tmp_path: Path) -> None:
    """``setup/`` is the author's: its suite giving no result is not the agent's failure.

    Without a baseline row a regression check graded a "new" scope and passed.
    """
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    (sample_dir / "setup" / "conftest.py").write_text("import os\nos._exit(0)\n", encoding="utf-8")
    sample = _make_sample(sample_dir, gate=_exec_gate())

    with pytest.raises(BaselineSuiteError, match=r"exited 0 with no junit report"):
        FakeRunner().run_sample(sample, tmp_path / "scratch")


def test_the_scoring_suite_leaves_no_coverage_data_in_the_candidate_tree(tmp_path: Path) -> None:
    """Regression: pytest-cov wrote ``.coverage`` into the tree, one path shared by ``--jobs``."""
    result = _run_suite_green(tmp_path, {"mod.py": _REFACTORED})

    assert result.passed is True
    assert not (tmp_path / "scratch" / ".coverage").exists()


def test_score_itself_checks_the_suite_toolchain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``score`` called without the runner's preflight still refuses a missing toolchain."""
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.scoring._importable", lambda name: name != "pytest"
    )
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_suite_green_gate())
    baseline = materialize(sample, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, "transcript")

    with pytest.raises(SuiteToolchainError, match=r"cannot import pytest:"):
        score(sample, baseline, candidate)


def test_a_missing_suite_toolchain_stops_the_sample_before_the_agent_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: no pytest-cov scored every trial 0, the environment's fault charged to the agent.

    The check runs in this process: a ``pytest.py`` in the candidate tree can fake
    any output the suite's subprocess prints, but not what this interpreter imports.
    """
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.scoring._importable", lambda name: name != "pytest_cov"
    )
    ran: list[Path] = []
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_suite_green_gate())

    with pytest.raises(SuiteToolchainError, match=r"pytest_cov"):
        FakeRunner(ran.append).run_sample(sample, tmp_path / "scratch")
    assert ran == []


def test_a_sample_that_runs_no_suite_needs_no_suite_toolchain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only a sample whose checks run the suite needs pytest and pytest-cov."""
    monkeypatch.setattr("coding_agent_playbook.evals.run.scoring._importable", lambda name: False)
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_sample(
        sample, tmp_path / "scratch"
    )

    assert result.passed is True


# --------------------------------------------------------------------------- #
# Verdict + no-judge invariant
# --------------------------------------------------------------------------- #


def test_gate_only_verdict_equals_the_gate(tmp_path: Path) -> None:
    """A gate-only sample's verdict is the gate layer's pass/fail."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_sample(
        sample, tmp_path / "scratch"
    )
    gate = _check(result.report, "gate")
    assert result.passed == gate.passed


def test_deterministic_only_verdict_is_the_gate_when_rubric_skips(tmp_path: Path) -> None:
    """With no judge, the rubric layer's judged content skips; the verdict = gate.

    The rubric layer is present (``gate and rubric``) but its judged ThresholdCheck
    is unavailable without ``ctx.judge`` — so the verdict reduces to the gate
    (skipped-neutral): a passing gate => a passing trial.
    """
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity", "naming"))

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_sample(
        sample, tmp_path / "scratch"
    )

    # The inner judged checks never ran (no judge).
    assert not any(d.evaluator.startswith("judge:") for d in _scope_details(result.report))
    gate = _check(result.report, "gate")
    assert gate.passed is True
    # Verdict == gate (rubric layer is skipped-neutral).
    assert result.passed is True


def test_no_judge_rubric_layer_is_skipped_not_a_vacuous_pass(tmp_path: Path) -> None:
    """With no judge the rubric layer is *skipped*, so ``gate or rubric`` needs the gate.

    Regression: the rubric layer (an ``AllOf`` over judged checks) used to run
    with every child unavailable and report a vacuous ``passed=True`` — so
    ``gate or rubric`` passed a sample whose gate failed. ``fail_fast=False`` keeps
    the JUDGED tier from being short-circuited, so the layer is really scheduled.
    """
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {
        "expr": "made",
        "bind": {"made": {"check": "file_exists", "path": "never_created.py"}},
    }
    sample = _make_sample(
        sample_dir, gate=gate, rubric=_judged_rubric("clarity"), verdict="gate or rubric"
    )

    result = FakeRunner().run_sample(sample, tmp_path / "scratch", fail_fast=False)

    assert _check(result.report, "rubric").status == "skipped"
    assert result.passed is False


def test_score_is_callable_directly_with_handles(tmp_path: Path) -> None:
    """``score(sample, baseline, candidate)`` works without going through run_sample."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())

    baseline = materialize(sample, tmp_path / "scratch")
    write_files({"mod.py": _REFACTORED})(baseline.repo_root)
    candidate = capture(baseline.repo_root, baseline, "transcript")
    assert isinstance(baseline, Baseline)
    assert isinstance(candidate, Candidate)

    report = score(sample, baseline, candidate)
    assert report.passed is True


# --------------------------------------------------------------------------- #
# Judged [rubric] scoring (hermetic via StubJudge)
# --------------------------------------------------------------------------- #


def test_judged_rubric_passes_with_a_high_judge(tmp_path: Path) -> None:
    """A [rubric] sample run via FakeRunner + a high StubJudge passes the rubric layer."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity", "naming"))

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_sample(
        sample, tmp_path / "scratch", judge=StubJudge({"clarity": 0.9, "naming": 0.7})
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

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity"))

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    # composite 0.3 < 0.5 floor => rubric layer fails.
    result = runner.run_sample(sample, tmp_path / "scratch", judge=StubJudge({"clarity": 0.3}))

    rubric = _check(result.report, "rubric")
    assert rubric.passed is False
    # gate passes but rubric fails => "gate and rubric" verdict is False.
    assert _check(result.report, "gate").passed is True
    assert result.passed is False


def test_no_judge_preserves_deterministic_only_behaviour(tmp_path: Path) -> None:
    """With no judge, the rubric's judged content skips; the verdict = gate."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate(), rubric=_judged_rubric("clarity", "naming"))

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_sample(
        sample, tmp_path / "scratch"
    )

    assert not any(d.evaluator.startswith("judge:") for d in _scope_details(result.report))
    assert result.passed is True


def test_judge_samples_threaded_through_to_the_judge(tmp_path: Path) -> None:
    """``run_sample(judge_samples=N)`` reaches the judge as the per-criterion ``n``."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, rubric=_judged_rubric("clarity"), verdict="rubric")

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(write_files({"mod.py": _REFACTORED})).run_sample(
        sample, tmp_path / "scratch", judge=judge, judge_samples=5
    )
    assert judge.calls == [("clarity", judge.calls[0][1], 5)]


def test_judge_artifact_is_the_candidate_diff(tmp_path: Path) -> None:
    """The judged artifact is the candidate's captured git diff (the agent's change)."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, rubric=_judged_rubric("clarity"), verdict="rubric")

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(write_files({"helper.py": "answer = 42\n"})).run_sample(
        sample, tmp_path / "scratch", judge=judge
    )
    _criterion, artifact, _n = judge.calls[0]
    assert "answer = 42" in str(artifact)


def test_judge_artifact_prefers_the_diff_over_the_transcript(tmp_path: Path) -> None:
    """Back-compat: an edit sample grades the diff, never the transcript."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, rubric=_judged_rubric("clarity"), verdict="rubric")

    judge = StubJudge({"clarity": 0.8})
    FakeRunner(
        write_files({"helper.py": "answer = 42\n"}), transcript="TRANSCRIPT-SENTINEL"
    ).run_sample(sample, tmp_path / "scratch", judge=judge)

    _criterion, artifact, _n = judge.calls[0]
    assert "answer = 42" in str(artifact)
    assert "TRANSCRIPT-SENTINEL" not in str(artifact)


def test_judge_artifact_falls_back_to_the_transcript_when_the_diff_is_empty(
    tmp_path: Path,
) -> None:
    """A review-only sample produces no diff, so the agent's *answer* is graded.

    Regression guard: review samples (a ``file_unchanged`` gate) are graded on what
    the agent *said*, and a no-op agent leaves ``candidate.diff`` empty. Grading
    the diff unconditionally handed every such sample an empty artifact, so the
    judge scored nothing at all.
    """
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, rubric=_judged_rubric("clarity"), verdict="rubric")

    judge = StubJudge({"clarity": 0.8})
    # Default no-op mutation => the agent edited nothing => empty diff.
    FakeRunner(transcript="I found an OS command injection in app/jobs.py.").run_sample(
        sample, tmp_path / "scratch", judge=judge
    )

    _criterion, artifact, _n = judge.calls[0]
    assert "OS command injection" in str(artifact)


# --------------------------------------------------------------------------- #
# Fail-fast: a lost deterministic gate skips the judge tier
# --------------------------------------------------------------------------- #


def test_fail_fast_skips_the_judge_when_a_gate_check_fails(tmp_path: Path) -> None:
    """fail_fast (the runner default) skips the judge tier once the gate is lost."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    # A gate check the no-op agent will violate (the file is never created).
    gate = {
        "expr": "made",
        "bind": {"made": {"check": "file_exists", "path": "never_created.py"}},
    }
    sample = _make_sample(sample_dir, gate=gate, rubric=_judged_rubric("clarity"))

    judge = StubJudge({"clarity": 0.9})
    result = FakeRunner().run_sample(sample, tmp_path / "scratch", judge=judge)

    assert result.passed is False
    # The judge was never invoked.
    assert judge.calls == []
    # The rubric layer is recorded skipped, not run.
    assert _check(result.report, "rubric").status == "skipped"


def test_full_scoring_runs_the_judge_even_after_a_failed_gate(tmp_path: Path) -> None:
    """fail_fast=False (``--full-scoring``) grades the judge tier regardless."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {
        "expr": "made",
        "bind": {"made": {"check": "file_exists", "path": "never_created.py"}},
    }
    sample = _make_sample(sample_dir, gate=gate, rubric=_judged_rubric("clarity"))

    judge = StubJudge({"clarity": 0.9})
    result = FakeRunner().run_sample(sample, tmp_path / "scratch", judge=judge, fail_fast=False)

    # Gate still lost (the expected check failed)...
    assert result.passed is False
    # ...but full scoring graded the judge anyway.
    assert judge.calls == [("clarity", judge.calls[0][1], 1)]
    assert _check(result.report, "rubric").status == "run"


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_ruff_violations_stays_unavailable_in_an_eval_sample(tmp_path: Path) -> None:
    """Eval scoring passes no ``tool_paths``, so a ``ruff_violations`` check is skipped.

    The measuring pass promises only what it can run (specs/prT-package-layout.md
    B.3 item 13): the cyclomatic-complexity check beside it still runs.
    """
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {
        "expr": "cc and ruff",
        "bind": {
            "cc": {"check": "non_regression", "metric": "cyclomatic_complexity", "warn": 0.5},
            "ruff": {"check": "threshold", "metric": "ruff_violations", "fail": 0.5},
        },
    }
    sample = _make_sample(sample_dir, gate=gate)

    result = FakeRunner().run_sample(sample, tmp_path / "scratch")

    assert _check(result.report, "threshold:ruff_violations").status == "skipped"
    assert _check(result.report, "nonreg:cyclomatic_complexity").status == "run"


def test_materialize_with_no_setup_dir_yields_empty_baseline(tmp_path: Path) -> None:
    """A sample whose ``setup/`` is missing still produces a committed empty repo."""
    sample_dir = tmp_path / "sample"  # no setup/ created
    sample_dir.mkdir()
    sample = _make_sample(sample_dir, gate=_cc_gate())

    baseline = materialize(sample, tmp_path / "scratch")
    assert baseline.commit
    assert baseline.setup_snapshot.is_dir()
    assert not any(baseline.setup_snapshot.iterdir())  # empty snapshot


@pytest.mark.catalog
def test_render_prompt_skips_non_matching_prompts() -> None:
    """Resolution scans every prompt md and returns only the id-matching one."""
    sample_dir = CORE_ROOT / "eval_samples" / "explain" / "pure-function"

    sample = EvalSample(
        id="explain-pure-function",
        prompt_id="explain",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="coding_agent_playbook",
    )
    prompt = render_prompt(sample)
    assert prompt
    assert "[prompt:explain]" not in prompt  # i.e. not the placeholder fallback


# --------------------------------------------------------------------------- #
# Weighted-composite verdict (C10) — end-to-end through the runner + scoring
# --------------------------------------------------------------------------- #


def test_weighted_verdict_e2e_threads_composite_into_report(tmp_path: Path) -> None:
    """End-to-end: weighted ``[verdict]`` populates ``report.verdict_score`` + ``passed``."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(
        sample_dir,
        gate=_cc_gate(),
        rubric=_judged_rubric("clarity"),
        verdict_block={"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.7},
    )

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    # gate's CC clears -> layer mean 1.0; judge gives rubric composite 0.9.
    # verdict_score = 0.4*1.0 + 0.6*0.9 = 0.94 >= 0.7 -> pass.
    result = runner.run_sample(sample, tmp_path / "scratch", judge=StubJudge({"clarity": 0.9}))
    assert result.report.verdict_score is not None
    assert result.report.verdict_score == pytest.approx(0.94)
    assert result.passed is True


def test_weighted_verdict_e2e_below_threshold_fails(tmp_path: Path) -> None:
    """A weighted composite landing below ``fail`` fails the trial."""
    from coding_agent_playbook.evals.judge import StubJudge

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(
        sample_dir,
        gate=_cc_gate(),
        rubric=_judged_rubric("clarity"),
        verdict_block={"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.7},
    )

    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    # gate ok -> 1.0; judge gives rubric composite 0.2.
    # verdict_score = 0.4*1.0 + 0.6*0.2 = 0.52 < 0.7 -> fail.
    result = runner.run_sample(sample, tmp_path / "scratch", judge=StubJudge({"clarity": 0.2}))
    assert result.report.verdict_score == pytest.approx(0.52)
    assert result.passed is False


def test_weighted_verdict_deterministic_only_renormalizes_skipped_rubric(
    tmp_path: Path,
) -> None:
    """With no judge, the rubric layer skips and gate's weight renormalizes to 1.0."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(
        sample_dir,
        gate=_cc_gate(),
        rubric=_judged_rubric("clarity"),
        verdict_block={"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.7},
    )

    # No judge -> rubric layer skipped. gate score is 1.0 (CC cleared).
    # Renormalized: only gate contributes -> verdict_score = 1.0 -> pass.
    runner = FakeRunner(write_files({"mod.py": _REFACTORED}))
    result = runner.run_sample(sample, tmp_path / "scratch")
    assert result.report.verdict_score == pytest.approx(1.0)
    assert result.passed is True


def test_boolean_verdict_leaves_verdict_score_none(tmp_path: Path) -> None:
    """Boolean-mode verdict (today): ``report.verdict_score`` stays ``None``."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_cc_gate())

    result = FakeRunner(write_files({"mod.py": _REFACTORED})).run_sample(
        sample, tmp_path / "scratch"
    )
    assert result.report.verdict_score is None
    assert result.passed is True


# --------------------------------------------------------------------------- #
# C11: setup/pyproject.toml is uv-sync'd before the agent runs
# --------------------------------------------------------------------------- #


def test_uv_sync_skipped_when_no_pyproject(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A deps-less fixture (no ``pyproject.toml``) never shells out to ``uv``.

    ``uv`` is only required when the scratch tree carries a ``pyproject.toml``;
    a fixture with no Python deps must stay uv-free (the existing 1190+ tests
    that lay down a bare ``setup/`` directory work unchanged).
    """
    calls: list[list[str]] = []

    def _capture_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.subprocess.run", _capture_run
    )

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)  # lays down mod.py + test_mod.py; NO pyproject.toml.
    sample = _make_sample(sample_dir, gate=_cc_gate())

    materialize(sample, tmp_path / "scratch")

    # The only ``subprocess.run`` calls were the git invocations; none were uv.
    assert not any(a and a[0] == "uv" for a in calls)


def test_uv_sync_invoked_when_pyproject_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A scratch tree with a ``pyproject.toml`` triggers one ``uv sync`` per tree.

    The fake ``subprocess.run`` captures both invocations (the scratch repo and
    the pristine ``setup/`` snapshot — the execution baseline) so we can assert
    each one ran from the right cwd.
    """
    uv_calls: list[tuple[list[str], Path]] = []
    real_run = subprocess.run

    def _capture_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            uv_calls.append((list(args), Path(kwargs.get("cwd", "."))))
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.subprocess.run", _capture_run
    )
    # Pretend ``uv`` is on PATH (we never actually shell out to it).
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _binary: "/fake/uv"
    )

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    (sample_dir / "setup" / "pyproject.toml").write_text(
        '[project]\nname = "fx"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    sample = _make_sample(sample_dir, gate=_cc_gate())

    baseline = materialize(sample, tmp_path / "scratch")

    # Two ``uv sync`` calls: one in the scratch repo, one in the pristine snapshot.
    assert len(uv_calls) == 2
    cwds = {call[1] for call in uv_calls}
    assert baseline.repo_root in cwds
    assert baseline.setup_snapshot in cwds
    # Without a uv.lock the runner falls back to the non-frozen form (it
    # resolves + locks on the fly — the right default for a fresh fixture).
    for args, _cwd in uv_calls:
        assert args[:2] == ["uv", "sync"]
        assert "--frozen" not in args


def test_uv_sync_uses_frozen_when_lock_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When ``uv.lock`` exists the runner passes ``--frozen`` for reproducibility."""
    uv_args: list[list[str]] = []
    real_run = subprocess.run

    def _capture_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            uv_args.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.subprocess.run", _capture_run
    )
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _binary: "/fake/uv"
    )

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    (sample_dir / "setup" / "pyproject.toml").write_text(
        '[project]\nname = "fx"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    (sample_dir / "setup" / "uv.lock").write_text("# stub\n", encoding="utf-8")
    sample = _make_sample(sample_dir, gate=_cc_gate())

    materialize(sample, tmp_path / "scratch")

    assert uv_args, "expected uv sync to run"
    for args in uv_args:
        assert args == ["uv", "sync", "--frozen"]


def test_uv_sync_raises_clear_error_when_uv_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fixture with a ``pyproject.toml`` but no ``uv`` on PATH raises a clear error."""
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _binary: None
    )

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    (sample_dir / "setup" / "pyproject.toml").write_text(
        '[project]\nname = "fx"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    sample = _make_sample(sample_dir, gate=_cc_gate())

    with pytest.raises(RuntimeError, match="uv binary required"):
        materialize(sample, tmp_path / "scratch")


def test_uv_sync_raises_clear_error_when_sync_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A nonzero ``uv sync`` is surfaced as a clear RuntimeError carrying stderr."""
    real_run = subprocess.run

    def _capture_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 1, "", "lockfile out of sync")
        return real_run(args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.subprocess.run", _capture_run
    )
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _binary: "/fake/uv"
    )

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    (sample_dir / "setup" / "pyproject.toml").write_text(
        '[project]\nname = "fx"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    sample = _make_sample(sample_dir, gate=_cc_gate())

    with pytest.raises(RuntimeError, match=r"uv sync failed.*lockfile out of sync"):
        materialize(sample, tmp_path / "scratch")


# --------------------------------------------------------------------------- #
# An agent stopped at its timeout
# --------------------------------------------------------------------------- #


class _TimingOutRunner(FakeRunner):
    """A fake agent that applies its mutation, then outlives its timeout with partial output."""

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        super()._invoke_agent(prompt, scratch_dir)
        raise subprocess.TimeoutExpired(["agent"], 600, output=b"half an answer SECRET-0")

    def _redact(self, text: str) -> str:
        return text.replace("SECRET-0", "[redacted]")


def _helper_gate() -> dict[str, Any]:
    return {"expr": "made", "bind": {"made": {"check": "file_exists", "path": "helper.py"}}}


@pytest.mark.parametrize(("files", "passed"), [({"helper.py": "x = 1\n"}, True), ({}, False)])
def test_an_agent_stopped_at_its_timeout_is_a_scored_trial(
    tmp_path: Path, files: dict[str, str], passed: bool
) -> None:
    """Regression: one run past the timeout raised out of ``--record`` and lost every metric."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_helper_gate())

    result = _TimingOutRunner(write_files(files)).run_sample(sample, tmp_path / "scratch")

    assert result.passed is passed  # graded on the tree the agent left
    assert "[the agent was stopped at its 600 s timeout]" in result.transcript
    assert "half an answer [redacted]" in result.transcript
    assert "SECRET-0" not in result.transcript


@pytest.mark.parametrize(
    ("stdout", "stderr", "transcript"),
    [
        (None, None, "[the agent was stopped at its 1.5 s timeout]"),
        ("out", "err", "out\nerr\n[the agent was stopped at its 1.5 s timeout]"),
        (b"\xffbytes", None, "�bytes\n[the agent was stopped at its 1.5 s timeout]"),
    ],
)
def test_timed_out_run_keeps_the_partial_output(
    stdout: bytes | str | None, stderr: bytes | str | None, transcript: str
) -> None:
    exc = subprocess.TimeoutExpired(["agent"], 1.5, output=stdout, stderr=stderr)

    run = timed_out_run(exc, str)

    assert (run.returncode, run.transcript) == (TIMED_OUT_RETURNCODE, transcript)
