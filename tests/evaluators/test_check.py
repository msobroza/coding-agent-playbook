"""Tests for the deterministic ``Check`` layer (T3) - ``evaluators/check.py``.

These port the per-scope decision cases from ``test_grade.py`` /
``test_grade_inverted.py`` (absolute warn/fail, threshold override, the
inclusive-at-bound vs strict-below boundary rule, regression detection /
tolerance / new-scope-absolute-fallback / removed-scope-ignored) and the file
predicate cases from ``test_expected.py``, but assert on the **Check** shapes:
``result.subresults[i].level``/``.score`` + ``result.passed`` rather than
``report.findings``. The metric-backed checks read the same boundary logic
``grade()`` does (copied, not imported), so the asserted levels match exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.check import (
    MeasurementSet,
    NonRegressionCheck,
    ThresholdCheck,
)
from coding_agent_playbook.evaluators.checks.files import (
    FileContainsCheck,
    FileExistsCheck,
    FileForbiddenCheck,
    FileUnchangedCheck,
)
from coding_agent_playbook.evaluators.metric import Metric
from coding_agent_playbook.evaluators.scope import CostTier, Determinism, Scope
from coding_agent_playbook.evaluators.types import (
    CheckResult,
    EvalContext,
    Measurement,
    ScopeDetail,
)

if TYPE_CHECKING:
    from pathlib import Path


# --------------------------------------------------------------------------- #
# Test metrics: one higher-is-worse (CC-like), one higher-is-better (cov-like).
# The Check holds its own thresholds, so the metric only supplies name +
# direction + needs_project (no thresholds live on a Metric anymore).
# --------------------------------------------------------------------------- #


class _CC(Metric):
    name = "cyclomatic_complexity"
    scope = Scope.FUNCTION
    higher_is_worse = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


class _Cov(Metric):
    name = "coverage"
    scope = Scope.FILE
    higher_is_worse = False
    needs_project = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


def _ctx() -> EvalContext:
    return EvalContext(module=None, source="", label="check")


def _ms(candidate: list[Measurement], baseline: list[Measurement] | None = None) -> MeasurementSet:
    return MeasurementSet(candidate, baseline)


def _cc(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="cyclomatic_complexity", scope_key=scope, value=value)


def _cov(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="coverage", scope_key=scope, value=value)


def _details(result: CheckResult) -> list[ScopeDetail]:
    """Narrow a result's ``subresults`` to the leaf :class:`ScopeDetail` rows.

    The deterministic checks only ever emit ``ScopeDetail`` leaves (never nested
    ``CheckResult`` rows), so this asserts that and gives the type checker a
    concrete element type to read ``.level``/``.scope_key``/... off.
    """
    out: list[ScopeDetail] = []
    for d in result.subresults:
        assert isinstance(d, ScopeDetail)
        out.append(d)
    return out


# --------------------------------------------------------------------------- #
# ThresholdCheck - absolute mode (higher-is-worse), ported from test_grade.py
# --------------------------------------------------------------------------- #


def test_threshold_absolute_warn_and_fail() -> None:
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    ms = _ms([_cc("a.py::warn", 12), _cc("a.py::fl", 25), _cc("a.py::ok", 3)])
    result = check.grade(_ctx(), ms)
    levels = {d.scope_key: d.level for d in _details(result)}
    assert levels["a.py::warn"] == "warn"
    assert levels["a.py::fl"] == "fail"
    assert levels["a.py::ok"] == "ok"
    assert result.passed is False  # one scope failed
    assert len(result.subresults) == 3


def test_threshold_passes_when_only_warnings() -> None:
    # A warn does NOT fail the check (strict is a Rubric-level concern).
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    result = check.grade(_ctx(), _ms([_cc("a.py::w", 12)]))
    assert _details(result)[0].level == "warn"
    assert result.passed is True


def test_threshold_override_changes_level() -> None:
    # 12 is a warn under warn=10/fail=20, but ok under the raised warn=20.
    check = ThresholdCheck(_CC(), warn=20, fail=40)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 12)]))
    assert _details(result)[0].level == "ok"
    assert result.passed is True


def test_threshold_kind_new_without_baseline() -> None:
    # No baseline => the scope is "new" and graded against the absolute bounds.
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 25)]))
    assert _details(result)[0].kind == "new"
    assert _details(result)[0].bound == 20


def test_threshold_kind_absolute_with_baseline() -> None:
    # With a baseline match, absolute mode grades kind "absolute" (mirrors _decide).
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 25)], [_cc("a.py::f", 25)]))
    assert _details(result)[0].kind == "absolute"
    assert _details(result)[0].bound == 20


def test_threshold_ignores_baseline_in_absolute_mode() -> None:
    # baseline is far worse, but absolute mode ignores it entirely.
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    ms = _ms([_cc("a.py::f", 3)], [_cc("a.py::f", 25)])
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "ok"


# --------------------------------------------------------------------------- #
# ThresholdCheck - scores / ramps (ported from test_grade composite cases)
# --------------------------------------------------------------------------- #


def test_threshold_score_ramps_partial() -> None:
    # CC=15 midway between warn(10)/fail(20) => ramp score 0.5.
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 15)]))
    assert _details(result)[0].score == pytest.approx(0.5)
    assert result.score == pytest.approx(0.5)


def test_threshold_score_at_or_under_warn_is_one() -> None:
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 5)]))
    assert _details(result)[0].score == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# ThresholdCheck - boundary semantics (ported from test_grade_inverted.py)
# --------------------------------------------------------------------------- #


def test_threshold_boundary_higher_is_worse_inclusive() -> None:
    # higher_is_worse: value AT the bound breaches (>=).
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    ms = _ms([_cc("a.py::fl", 20), _cc("a.py::wn", 10), _cc("a.py::ok", 9)])
    result = check.grade(_ctx(), ms)
    levels = {d.scope_key: d.level for d in _details(result)}
    assert levels["a.py::fl"] == "fail"  # 20 >= fail(20)
    assert levels["a.py::wn"] == "warn"  # 10 >= warn(10)
    assert levels["a.py::ok"] == "ok"  # 9 < warn


def test_threshold_boundary_higher_is_better_strict_warn() -> None:
    # higher_is_better: value AT warn is ok (strict <), below warn is warn.
    check = ThresholdCheck(_Cov(), warn=80, fail=60)
    at_warn = check.grade(_ctx(), _ms([_cov("a.py", 80.0)]))
    assert _details(at_warn)[0].level == "ok"  # 80 < 80 is False
    below_warn = check.grade(_ctx(), _ms([_cov("a.py", 79.0)]))
    assert _details(below_warn)[0].level == "warn"  # 79 < 80


def test_threshold_boundary_higher_is_better_strict_fail() -> None:
    # higher_is_better: value AT fail is ok (strict <), below fail is fail.
    check = ThresholdCheck(_Cov(), warn=80, fail=60)
    at_fail = check.grade(_ctx(), _ms([_cov("a.py", 60.0)]))
    assert _details(at_fail)[0].level == "warn"  # 60 < 80 warn, but 60 < 60 fail is False
    below_fail = check.grade(_ctx(), _ms([_cov("a.py", 55.0)]))
    assert _details(below_fail)[0].level == "fail"  # 55 < 60


def test_threshold_higher_is_better_inverted_levels() -> None:
    # Ported from test_inverted_absolute_warn_and_fail.
    check = ThresholdCheck(_Cov(), warn=80, fail=60)
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 70)])))[0].level == "warn"
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 55)])))[0].level == "fail"
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 95)])))[0].level == "ok"


def test_threshold_min_score_sugar_sets_fail() -> None:
    # min_score=20 == fail=20.
    a = ThresholdCheck(_CC(), warn=10, min_score=20)
    b = ThresholdCheck(_CC(), warn=10, fail=20)
    ra = a.grade(_ctx(), _ms([_cc("a.py::f", 25)]))
    rb = b.grade(_ctx(), _ms([_cc("a.py::f", 25)]))
    assert _details(ra)[0].level == _details(rb)[0].level == "fail"


# --------------------------------------------------------------------------- #
# ThresholdCheck - descriptors / cost tier
# --------------------------------------------------------------------------- #


def test_threshold_descriptors_static_metric() -> None:
    check = ThresholdCheck(_CC(), warn=10, fail=20, weight=2.0, required=False)
    assert check.id == "threshold:cyclomatic_complexity"
    assert check.weight == 2.0
    assert check.required is False
    assert check.determinism is Determinism.DETERMINISTIC
    assert check.cost is CostTier.DETERMINISTIC  # static metric


def test_threshold_cost_execution_for_needs_project_metric() -> None:
    check = ThresholdCheck(_Cov(), warn=80, fail=60)
    assert check.cost is CostTier.EXECUTION  # coverage needs_project


def test_threshold_zero_scopes_passes_with_none_score() -> None:
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    result = check.grade(_ctx(), _ms([]))
    assert result.subresults == ()
    assert result.score is None
    assert result.passed is True


# --------------------------------------------------------------------------- #
# NonRegressionCheck - regression mode (ported from test_grade.py)
# --------------------------------------------------------------------------- #


def test_nonreg_detected_on_worsened_scope() -> None:
    check = NonRegressionCheck(_CC())  # max_worsening default 0
    ms = _ms([_cc("a.py::f", 8)], [_cc("a.py::f", 5)])  # worsened by 3
    result = check.grade(_ctx(), ms)
    d = _details(result)[0]
    assert d.level == "fail"
    assert d.kind == "regression"
    assert d.baseline == 5
    assert result.passed is False


def test_nonreg_pass_when_improved() -> None:
    check = NonRegressionCheck(_CC())
    ms = _ms([_cc("a.py::f", 5)], [_cc("a.py::f", 8)])  # improved
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "ok"
    assert result.passed is True


def test_nonreg_respects_tolerance() -> None:
    check = NonRegressionCheck(_CC(), max_worsening=2)
    ms = _ms([_cc("a.py::f", 6)], [_cc("a.py::f", 5)])  # worsened by 1, within band
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "ok"
    assert result.passed is True


def test_nonreg_higher_is_better_detects_drop() -> None:
    # coverage dropped 90 -> 85: worsening = base - cand = 5 > 0 => regression.
    check = NonRegressionCheck(_Cov())
    ms = _ms([_cov("a.py", 85)], [_cov("a.py", 90)])
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "fail"
    assert _details(result)[0].kind == "regression"


def test_nonreg_higher_is_better_pass_on_improvement() -> None:
    check = NonRegressionCheck(_Cov())
    ms = _ms([_cov("a.py", 95)], [_cov("a.py", 90)])
    assert _details(check.grade(_ctx(), ms))[0].level == "ok"


def test_nonreg_new_scope_falls_back_to_absolute() -> None:
    # No baseline match => kind "new", graded against the absolute warn/fail.
    check = NonRegressionCheck(_CC(), warn=10, fail=20)
    ms = _ms([_cc("a.py::new", 25)], [])  # > fail(20)
    result = check.grade(_ctx(), ms)
    d = _details(result)[0]
    assert d.kind == "new"
    assert d.level == "fail"
    assert d.baseline is None
    assert result.passed is False


def test_nonreg_new_scope_ok_under_warn() -> None:
    check = NonRegressionCheck(_CC(), warn=10, fail=20)
    ms = _ms([_cc("a.py::new", 3)], [])
    d = _details(check.grade(_ctx(), ms))[0]
    assert d.kind == "new"
    assert d.level == "ok"


def test_nonreg_removed_scope_is_ignored() -> None:
    # a.py::gone is only in the baseline; only candidate scopes are graded.
    check = NonRegressionCheck(_CC())
    ms = _ms([_cc("a.py::stay", 5)], [_cc("a.py::gone", 30), _cc("a.py::stay", 5)])
    result = check.grade(_ctx(), ms)
    scope_keys = {d.scope_key for d in _details(result)}
    assert scope_keys == {"a.py::stay"}


def test_nonreg_id_and_determinism() -> None:
    check = NonRegressionCheck(_CC())
    assert check.id == "nonreg:cyclomatic_complexity"
    assert check.determinism is Determinism.DETERMINISTIC


# --------------------------------------------------------------------------- #
# MeasurementSet.pairs - matching semantics
# --------------------------------------------------------------------------- #


def test_measurement_set_pairs_filters_by_metric_name() -> None:
    ms = _ms(
        [_cc("a.py::f", 1), _cov("a.py", 90)],
        [_cc("a.py::f", 2)],
    )
    pairs = ms.pairs("cyclomatic_complexity")
    assert pairs == [("a.py::f", 1.0, 2.0)]  # cov excluded; baseline attached


def test_measurement_set_pairs_new_scope_has_none_baseline() -> None:
    ms = _ms([_cc("a.py::new", 1)], [_cc("a.py::other", 2)])
    assert ms.pairs("cyclomatic_complexity") == [("a.py::new", 1.0, None)]


def test_measurement_set_pairs_no_baseline_list() -> None:
    ms = _ms([_cc("a.py::f", 1)])
    assert ms.pairs("cyclomatic_complexity") == [("a.py::f", 1.0, None)]


# --------------------------------------------------------------------------- #
# File checks - predicates (ported from test_expected.py), Check shapes
# --------------------------------------------------------------------------- #


def _tree_ctx(tree: Path | None, baseline_tree: Path | None = None) -> EvalContext:
    return EvalContext(
        module=None, source="", label="check", tree=tree, baseline_tree=baseline_tree
    )


def test_file_checks_descriptors() -> None:
    for check in (
        FileExistsCheck("a.py"),
        FileContainsCheck("a.py", "x"),
        FileUnchangedCheck("a.py"),
        FileForbiddenCheck("a.py"),
    ):
        assert check.determinism is Determinism.DETERMINISTIC
        assert check.cost is CostTier.DETERMINISTIC
        assert check.required is True
        assert check.weight == 0.0


def test_file_check_ids() -> None:
    assert FileExistsCheck("out.py").id == "file_exists:out.py"
    assert FileUnchangedCheck("src/m.py").id == "file_unchanged:src/m.py"
    assert FileForbiddenCheck("bad.py").id == "file_forbidden:bad.py"
    assert FileContainsCheck("out.py", "def foo").id == "file_contains:out.py~/def foo/"


# --- available() gating ------------------------------------------------------


def test_file_check_available_false_without_tree() -> None:
    assert FileExistsCheck("a.py").available(_tree_ctx(None)) is False


def test_file_check_available_true_with_tree(tmp_path: Path) -> None:
    assert FileExistsCheck("a.py").available(_tree_ctx(tmp_path)) is True


def test_file_unchanged_available_needs_baseline_tree(tmp_path: Path) -> None:
    assert FileUnchangedCheck("a.py").available(_tree_ctx(tmp_path, None)) is False
    base = tmp_path / "base"
    base.mkdir()
    assert FileUnchangedCheck("a.py").available(_tree_ctx(tmp_path, base)) is True


def test_file_check_without_tree_grades_fail() -> None:
    result = FileExistsCheck("a.py").grade(_tree_ctx(None), _ms([]))
    assert result.passed is False
    assert result.score == 0.0


# --- file_exists -------------------------------------------------------------


def test_file_exists_pass(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = FileExistsCheck("a.py").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is True
    assert result.score == 1.0
    assert _details(result)[0].scope_key == "a.py"
    assert _details(result)[0].level == "ok"


def test_file_exists_fail_when_missing(tmp_path: Path) -> None:
    result = FileExistsCheck("missing.py").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is False
    assert result.score == 0.0
    assert _details(result)[0].level == "fail"


def test_file_exists_fail_on_directory(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    result = FileExistsCheck("pkg").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is False  # a directory is not a regular file


# --- file_contains (regex) ---------------------------------------------------


def test_file_contains_pass_regex(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def _band(n):\n    return n\n", encoding="utf-8")
    result = FileContainsCheck("a.py", r"def _band\(").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is True
    assert result.score == 1.0


def test_file_contains_fail_no_match(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = FileContainsCheck("a.py", r"NOPE").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is False


def test_file_contains_fail_missing_file(tmp_path: Path) -> None:
    result = FileContainsCheck("missing.py", r".").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is False


# --- file_unchanged (vs baseline tree) ---------------------------------------


def test_file_unchanged_pass_identical(tmp_path: Path) -> None:
    cand, base = tmp_path / "cand", tmp_path / "base"
    cand.mkdir()
    base.mkdir()
    (cand / "a.py").write_text("same\n", encoding="utf-8")
    (base / "a.py").write_text("same\n", encoding="utf-8")
    result = FileUnchangedCheck("a.py").grade(_tree_ctx(cand, base), _ms([]))
    assert result.passed is True
    assert result.score == 1.0


def test_file_unchanged_fail_when_modified(tmp_path: Path) -> None:
    cand, base = tmp_path / "cand", tmp_path / "base"
    cand.mkdir()
    base.mkdir()
    (cand / "a.py").write_text("changed\n", encoding="utf-8")
    (base / "a.py").write_text("original\n", encoding="utf-8")
    result = FileUnchangedCheck("a.py").grade(_tree_ctx(cand, base), _ms([]))
    assert result.passed is False


def test_file_unchanged_fail_without_baseline_tree(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("same\n", encoding="utf-8")
    result = FileUnchangedCheck("a.py").grade(_tree_ctx(tmp_path, None), _ms([]))
    assert result.passed is False  # no baseline => cannot hold


def test_file_unchanged_fail_when_candidate_missing(tmp_path: Path) -> None:
    cand, base = tmp_path / "cand", tmp_path / "base"
    cand.mkdir()
    base.mkdir()
    (base / "a.py").write_text("original\n", encoding="utf-8")  # candidate lacks a.py
    result = FileUnchangedCheck("a.py").grade(_tree_ctx(cand, base), _ms([]))
    assert result.passed is False


# --- file_forbidden ----------------------------------------------------------


def test_file_forbidden_pass_when_absent(tmp_path: Path) -> None:
    result = FileForbiddenCheck("nope.py").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is True
    assert result.score == 1.0


def test_file_forbidden_fail_when_present(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("x = 1\n", encoding="utf-8")
    result = FileForbiddenCheck("bad.py").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is False


def test_file_forbidden_fail_when_dir_present(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    # exists(), not is_file(): a forbidden directory present also breaches.
    result = FileForbiddenCheck("__pycache__").grade(_tree_ctx(tmp_path), _ms([]))
    assert result.passed is False
