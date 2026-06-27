"""Tests for the execution evaluators ``test_pass_rate`` + ``coverage`` (M4).

These exercise the evaluators through their public ``available``/``evaluate``
surface against a real fixture project (inner pytest in a subprocess), plus the
grade-level gate/regression behaviour and the one-run caching guarantee when both
evaluators read the same handle.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evaluators import (
    EvalContext,
    Measurement,
    MetricConfig,
    grade,
)
from coding_agent_playbook.evaluators.execution.coverage import Coverage
from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.execution.test_pass import TestPassRate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_MOD = textwrap.dedent(
    """\
    def add(a, b):
        return a + b


    def sub(a, b):
        return a - b
    """
)

_TEST_PASS = textwrap.dedent(
    """\
    from mod import add, sub


    def test_add():
        assert add(1, 2) == 3


    def test_sub():
        assert sub(5, 2) == 3
    """
)

_TEST_FAIL = textwrap.dedent(
    """\
    from mod import add


    def test_add_ok():
        assert add(1, 2) == 3


    def test_add_broken():
        assert add(1, 2) == 99
    """
)


def _project(root: Path, reports: Path, test_source: str) -> ProjectHandle:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.py").write_text(_MOD, encoding="utf-8")
    (root / "test_mod.py").write_text(test_source, encoding="utf-8")
    return ProjectHandle.create(root, reports)


def _ctx(handle: ProjectHandle | None, label: str = "suite") -> EvalContext:
    return EvalContext(module=None, source="", label=label, project=handle)


# --------------------------------------------------------------------------- #
# availability / graceful skip
# --------------------------------------------------------------------------- #


def test_evaluators_unavailable_without_project() -> None:
    ctx = _ctx(None)
    assert TestPassRate().available(ctx) is False
    assert Coverage().available(ctx) is False
    # evaluate() degrades to [] rather than raising.
    assert TestPassRate().evaluate(ctx) == []
    assert Coverage().evaluate(ctx) == []


def test_evaluators_available_with_project(tmp_path: Path) -> None:
    handle = _project(tmp_path / "proj", tmp_path / "rep", _TEST_PASS)
    ctx = _ctx(handle)
    assert TestPassRate().available(ctx) is True
    assert Coverage().available(ctx) is True


# --------------------------------------------------------------------------- #
# values
# --------------------------------------------------------------------------- #


def test_test_pass_rate_all_pass_is_one(tmp_path: Path) -> None:
    handle = _project(tmp_path / "proj", tmp_path / "rep", _TEST_PASS)
    ms = TestPassRate().evaluate(_ctx(handle))
    assert len(ms) == 1
    assert ms[0].value == 1.0
    assert ms[0].scope_key == "suite"


def test_test_pass_rate_with_failure_below_one(tmp_path: Path) -> None:
    handle = _project(tmp_path / "proj", tmp_path / "rep", _TEST_FAIL)
    ms = TestPassRate().evaluate(_ctx(handle))
    assert ms[0].value == 0.5


def test_coverage_emits_per_file_and_module_total(tmp_path: Path) -> None:
    handle = _project(tmp_path / "proj", tmp_path / "rep", _TEST_PASS)
    ms = Coverage().evaluate(_ctx(handle, label="suite"))
    # one MODULE total (keyed "suite") + at least the mod.py file.
    keys = {m.scope_key for m in ms}
    assert "suite" in keys
    assert any(k.endswith("mod.py") for k in keys)
    # The passing suite hits both add() and sub(), so mod.py is fully covered.
    file_m = next(m for m in ms if m.scope_key.endswith("mod.py"))
    assert file_m.value == 100.0


# --------------------------------------------------------------------------- #
# one-run caching across both evaluators
# --------------------------------------------------------------------------- #


def test_both_evaluators_share_one_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running both evaluators against one handle runs the suite exactly once."""
    handle = _project(tmp_path / "proj", tmp_path / "rep", _TEST_PASS)

    import subprocess as _subprocess

    calls = {"n": 0}
    real = _subprocess.run

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.execution.project.subprocess.run",
        _counting,
    )
    ctx = _ctx(handle)
    TestPassRate().evaluate(ctx)
    Coverage().evaluate(ctx)
    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# grade-level gate + regression
# --------------------------------------------------------------------------- #


def _measure(handle: ProjectHandle, label: str = "suite") -> list[Measurement]:
    ctx = _ctx(handle, label=label)
    return TestPassRate().evaluate(ctx) + Coverage().evaluate(ctx)


def test_failing_suite_fails_absolute_gate(tmp_path: Path) -> None:
    handle = _project(tmp_path / "proj", tmp_path / "rep", _TEST_FAIL)
    report = grade(_measure(handle), None, MetricConfig(mode="absolute"))
    assert report.passed is False
    failing = [f for f in report.findings if f.evaluator == "test_pass_rate"]
    assert failing and failing[0].level == "fail"


def test_low_coverage_warns(tmp_path: Path) -> None:
    """A suite covering only one of two functions leaves mod.py under 80% -> warn."""
    partial = textwrap.dedent(
        """\
        from mod import add


        def test_add():
            assert add(1, 2) == 3
        """
    )
    handle = _project(tmp_path / "proj", tmp_path / "rep", partial)
    report = grade(_measure(handle), None, MetricConfig(mode="absolute"))
    cov_file = [
        f for f in report.findings if f.evaluator == "coverage" and f.scope_key.endswith("mod.py")
    ]
    assert cov_file and cov_file[0].level == "warn"
    assert cov_file[0].value < 80.0


def test_coverage_regression_drop_fails(tmp_path: Path) -> None:
    """Coverage dropping vs a baseline run fails regression mode; unchanged passes."""
    # Baseline: full coverage (both functions tested).
    base = _project(tmp_path / "base", tmp_path / "base_rep", _TEST_PASS)
    baseline_ms = _measure(base, label="suite")

    # Candidate: drops sub()'s coverage (only add tested).
    partial = textwrap.dedent(
        """\
        from mod import add


        def test_add():
            assert add(1, 2) == 3
        """
    )
    cand = _project(tmp_path / "cand", tmp_path / "cand_rep", partial)
    cand_ms = _measure(cand, label="suite")

    report = grade(cand_ms, baseline_ms, MetricConfig(mode="regression"))
    assert report.passed is False
    cov_reg = [
        f
        for f in report.findings
        if f.evaluator == "coverage" and f.kind == "regression" and f.level == "fail"
    ]
    assert cov_reg


def test_coverage_unchanged_passes_regression(tmp_path: Path) -> None:
    base = _project(tmp_path / "base", tmp_path / "base_rep", _TEST_PASS)
    baseline_ms = _measure(base, label="suite")
    cand = _project(tmp_path / "cand", tmp_path / "cand_rep", _TEST_PASS)
    cand_ms = _measure(cand, label="suite")
    report = grade(cand_ms, baseline_ms, MetricConfig(mode="regression"))
    assert report.passed is True


def test_new_failing_test_fails_regression(tmp_path: Path) -> None:
    base = _project(tmp_path / "base", tmp_path / "base_rep", _TEST_PASS)
    baseline_ms = _measure(base, label="suite")
    cand = _project(tmp_path / "cand", tmp_path / "cand_rep", _TEST_FAIL)
    cand_ms = _measure(cand, label="suite")
    report = grade(cand_ms, baseline_ms, MetricConfig(mode="regression"))
    assert report.passed is False
    tpr = [f for f in report.findings if f.evaluator == "test_pass_rate"]
    assert tpr and tpr[0].level == "fail"


# --------------------------------------------------------------------------- #
# flaky-retry
# --------------------------------------------------------------------------- #


def test_flaky_retry_recovers_pass_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With flaky_retries>0 a later attempt with a better pass rate is used.

    The handle's per-run parse is monkeypatched to yield a failing run first then
    a clean one, so ``best_pass_rate`` recovers to 1.0 without touching real I/O.
    """
    from coding_agent_playbook.evaluators.execution import project as project_mod
    from coding_agent_playbook.evaluators.execution.coverage_xml import CoverageReport
    from coding_agent_playbook.evaluators.execution.junit import JunitSummary

    handle = ProjectHandle.create(tmp_path / "proj", tmp_path / "rep", flaky_retries=2)

    flaky = JunitSummary(passed=1, failed=1, errors=0, skipped=0, total=2)  # 0.5
    clean = JunitSummary(passed=2, failed=0, errors=0, skipped=0, total=2)  # 1.0
    seq = [
        project_mod.RunArtifacts(junit=flaky, coverage=CoverageReport(), returncode=1),
        project_mod.RunArtifacts(junit=clean, coverage=CoverageReport(), returncode=0),
    ]

    def _fake_run_once(self: ProjectHandle) -> project_mod.RunArtifacts:
        return seq.pop(0)

    monkeypatch.setattr(ProjectHandle, "_run_once", _fake_run_once)
    assert handle.best_pass_rate() == 1.0


def test_flaky_retry_off_by_default_keeps_first_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coding_agent_playbook.evaluators.execution import project as project_mod
    from coding_agent_playbook.evaluators.execution.coverage_xml import CoverageReport
    from coding_agent_playbook.evaluators.execution.junit import JunitSummary

    handle = ProjectHandle.create(tmp_path / "proj", tmp_path / "rep")  # flaky_retries=0

    flaky = JunitSummary(passed=1, failed=1, errors=0, skipped=0, total=2)

    def _fake_run_once(self: ProjectHandle) -> project_mod.RunArtifacts:
        return project_mod.RunArtifacts(junit=flaky, coverage=CoverageReport(), returncode=1)

    monkeypatch.setattr(ProjectHandle, "_run_once", _fake_run_once)
    assert handle.best_pass_rate() == 0.5
