"""Tests for the deterministic ``Check`` layer (T3) - ``evaluators/check.py``.

Since the C3 normalization cutover the per-scope decision runs **entirely on the
metric's normalized ``0-1`` score** (higher = always better); the check's
``warn``/``fail`` are ``0-1`` cutoffs on that score and a scope breaches a bound
when its score is *strictly below* it.

The two stand-in metrics carry the real builtin normalizers:

* ``_CC`` (``cyclomatic_complexity``) ->
  :class:`~coding_agent_playbook.evaluators.normalizer.RampNormalizer`
  ``(good=5, bad=20)``, so ``score(raw) = clamp01((20 - raw) / 15)`` (raw 5 ->
  1.0, raw 12.5 -> 0.5, raw 20 -> 0.0).
* ``_Cov`` (``coverage``) ->
  :class:`~coding_agent_playbook.evaluators.normalizer.PercentNormalizer`, so
  ``score(raw) = clamp01(raw / 100)`` (raw 80 -> 0.8, raw 60 -> 0.6).

The file predicate cases (ported from ``test_expected.py``) are unchanged: they
set ``passed``/``score`` straight from the predicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.check import (
    MeasurementSet,
    NonRegressionCheck,
    ThresholdCheck,
)
from coding_agent_playbook.evaluators.checks.execution import CoverageCheck
from coding_agent_playbook.evaluators.checks.files import (
    FileContainsCheck,
    FileExistsCheck,
    FileForbiddenCheck,
    FileUnchangedCheck,
)
from coding_agent_playbook.evaluators.metric import Metric
from coding_agent_playbook.evaluators.normalizer import PercentNormalizer, RampNormalizer
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
# Test metrics carrying the real builtin normalizers: ``_CC`` ramps down as raw
# CC grows (RampNormalizer(good=5, bad=20)), ``_Cov`` is a 0-100 percentage
# (PercentNormalizer). The Check holds its own 0-1 thresholds, so the metric only
# supplies name + normalizer + needs_project (no thresholds live on a Metric).
# --------------------------------------------------------------------------- #


class _CC(Metric):
    name = "cyclomatic_complexity"
    scope = Scope.FUNCTION
    normalizer = RampNormalizer(good=5, bad=20)
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


class _Cov(Metric):
    name = "coverage"
    scope = Scope.FILE
    normalizer = PercentNormalizer()
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
# ThresholdCheck - absolute mode on normalized scores. Cutoffs warn=0.5,
# fail=0.25 (the cyclomatic_complexity defaults). With score = (20-raw)/15:
#   raw 5  -> 1.0   (ok)
#   raw 12 -> 0.533 (ok,  >= 0.5)
#   raw 14 -> 0.4   (warn, < 0.5, >= 0.25)
#   raw 17 -> 0.2   (fail, < 0.25)
#   raw 25 -> 0.0   (fail)
# --------------------------------------------------------------------------- #


def test_threshold_absolute_warn_and_fail() -> None:
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    ms = _ms([_cc("a.py::warn", 14), _cc("a.py::fl", 25), _cc("a.py::ok", 3)])
    result = check.grade(_ctx(), ms)
    levels = {d.scope_key: d.level for d in _details(result)}
    assert levels["a.py::warn"] == "warn"  # score 0.4
    assert levels["a.py::fl"] == "fail"  # score 0.0
    assert levels["a.py::ok"] == "ok"  # score 1.0
    assert result.passed is False  # one scope failed
    assert len(result.subresults) == 3


def test_threshold_passes_when_only_warnings() -> None:
    # A warn does NOT fail the check (strict is a Rubric-level concern).
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    result = check.grade(_ctx(), _ms([_cc("a.py::w", 14)]))  # score 0.4 -> warn
    assert _details(result)[0].level == "warn"
    assert result.passed is True


def test_threshold_override_changes_level() -> None:
    # raw 14 -> score 0.4 is a warn under warn=0.5, but ok under the lowered
    # warn=0.3 (0.4 >= 0.3).
    check = ThresholdCheck(_CC(), warn=0.3, fail=0.1)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 14)]))
    assert _details(result)[0].level == "ok"
    assert result.passed is True


def test_threshold_kind_new_without_baseline() -> None:
    # No baseline => the scope is "new" and graded against the absolute bounds.
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 25)]))  # score 0.0 -> fail
    assert _details(result)[0].kind == "new"
    assert _details(result)[0].bound == 0.25  # the 0-1 cutoff that decided


def test_threshold_kind_absolute_with_baseline() -> None:
    # With a baseline match, absolute mode grades kind "absolute" (mirrors _decide).
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 25)], [_cc("a.py::f", 25)]))
    assert _details(result)[0].kind == "absolute"
    assert _details(result)[0].bound == 0.25


def test_threshold_ignores_baseline_in_absolute_mode() -> None:
    # baseline is far worse, but absolute mode ignores it entirely.
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    ms = _ms([_cc("a.py::f", 3)], [_cc("a.py::f", 25)])  # cand score 1.0
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "ok"


# --------------------------------------------------------------------------- #
# ThresholdCheck - the per-scope score is the metric's normalized goodness.
# --------------------------------------------------------------------------- #


def test_threshold_score_ramps_partial() -> None:
    # CC=12.5 -> (20-12.5)/15 = 0.5 normalized goodness.
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 12.5)]))
    assert _details(result)[0].score == pytest.approx(0.5)
    assert result.score == pytest.approx(0.5)


def test_threshold_score_at_good_anchor_is_one() -> None:
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    result = check.grade(_ctx(), _ms([_cc("a.py::f", 5)]))  # at good anchor -> 1.0
    assert _details(result)[0].score == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# ThresholdCheck - boundary semantics: a score landing EXACTLY on a cutoff is ok
# (strict-below breach), and the raw value still rides on ``.value``.
# --------------------------------------------------------------------------- #


def test_threshold_boundary_strict_below_warn() -> None:
    # A score exactly AT warn is ok (strict <); just below is a warn.
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    at_warn = check.grade(_ctx(), _ms([_cc("a.py", 12.5)]))  # score 0.5
    assert _details(at_warn)[0].level == "ok"  # 0.5 < 0.5 is False
    below_warn = check.grade(_ctx(), _ms([_cc("a.py", 13)]))  # score 7/15 ~ 0.467
    assert _details(below_warn)[0].level == "warn"


def test_threshold_boundary_strict_below_fail() -> None:
    # A score exactly AT fail is a warn (it is below warn but not below fail);
    # just below fail is a fail.
    check = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    at_fail = check.grade(_ctx(), _ms([_cc("a.py", 16.25)]))  # score 3.75/15 = 0.25
    assert _details(at_fail)[0].level == "warn"  # 0.25 < 0.5 warn, 0.25 < 0.25 is False
    below_fail = check.grade(_ctx(), _ms([_cc("a.py", 17)]))  # score 0.2
    assert _details(below_fail)[0].level == "fail"


def test_threshold_coverage_percent_levels() -> None:
    # Coverage via PercentNormalizer; cutoffs warn=0.8, fail=0.6 land on the old
    # raw 80/60 boundaries (cov 80 -> 0.8, cov 60 -> 0.6).
    check = ThresholdCheck(_Cov(), warn=0.8, fail=0.6)
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 80)])))[0].level == "ok"  # 0.8
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 70)])))[0].level == "warn"  # 0.7
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 55)])))[0].level == "fail"  # 0.55
    assert _details(check.grade(_ctx(), _ms([_cov("a.py", 95)])))[0].level == "ok"  # 0.95
    # Raw value rides through unchanged on .value, score is normalized.
    one = _details(check.grade(_ctx(), _ms([_cov("a.py", 70)])))[0]
    assert one.value == 70
    assert one.score == pytest.approx(0.7)


@pytest.mark.parametrize(("raw", "level"), [(100.0, "ok"), (80.0, "ok"), (79.0, "warn")])
def test_coverage_check_at_100_percent_is_ok(raw: float, level: str) -> None:
    """prK §F.1.1 regression: the default bound is the 0-1 cutoff 0.8, not raw 80.0.

    ``PercentNormalizer`` never exceeds 1.0, so the old ``warn=80.0`` warned
    even at 100% coverage.
    """
    check = CoverageCheck()

    detail = _details(check.grade(_ctx(), _ms([_cov("a.py", raw)])))[0]

    assert detail.level == level
    assert detail.bound == (0.8 if level == "warn" else None)


def test_threshold_min_score_sugar_sets_fail() -> None:
    # min_score=0.25 == fail=0.25 (a 0-1 normalized floor now).
    a = ThresholdCheck(_CC(), warn=0.5, min_score=0.25)
    b = ThresholdCheck(_CC(), warn=0.5, fail=0.25)
    ra = a.grade(_ctx(), _ms([_cc("a.py::f", 25)]))  # score 0.0 -> fail
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
    # cand raw 8 -> score 0.8, base raw 5 -> score 1.0: the normalized score
    # dropped 0.2 > max_worsening(0) => regression. Raw baseline rides on .baseline.
    check = NonRegressionCheck(_CC())  # max_worsening default 0
    ms = _ms([_cc("a.py::f", 8)], [_cc("a.py::f", 5)])
    result = check.grade(_ctx(), ms)
    d = _details(result)[0]
    assert d.level == "fail"
    assert d.kind == "regression"
    assert d.baseline == 5  # RAW baseline preserved
    assert result.passed is False


def test_nonreg_pass_when_improved() -> None:
    # cand 5 -> 1.0, base 8 -> 0.8: score rose, no regression.
    check = NonRegressionCheck(_CC())
    ms = _ms([_cc("a.py::f", 5)], [_cc("a.py::f", 8)])  # improved
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "ok"
    assert result.passed is True


def test_nonreg_respects_tolerance() -> None:
    # cand raw 6 -> score 14/15 ~ 0.933, base raw 5 -> 1.0: score dropped ~0.067,
    # within the 0-1 tolerance band 0.1.
    check = NonRegressionCheck(_CC(), max_worsening=0.1)
    ms = _ms([_cc("a.py::f", 6)], [_cc("a.py::f", 5)])
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "ok"
    assert result.passed is True


def test_nonreg_coverage_detects_drop() -> None:
    # coverage 90 -> 85: scores 0.9 -> 0.85, dropped 0.05 > 0 => regression.
    check = NonRegressionCheck(_Cov())
    ms = _ms([_cov("a.py", 85)], [_cov("a.py", 90)])
    result = check.grade(_ctx(), ms)
    assert _details(result)[0].level == "fail"
    assert _details(result)[0].kind == "regression"


def test_nonreg_coverage_pass_on_improvement() -> None:
    check = NonRegressionCheck(_Cov())
    ms = _ms([_cov("a.py", 95)], [_cov("a.py", 90)])  # 0.95 > 0.90
    assert _details(check.grade(_ctx(), ms))[0].level == "ok"


def test_nonreg_new_scope_falls_back_to_absolute() -> None:
    # No baseline match => kind "new", graded against the absolute 0-1 warn/fail.
    check = NonRegressionCheck(_CC(), warn=0.5, fail=0.25)
    ms = _ms([_cc("a.py::new", 25)], [])  # score 0.0 < fail(0.25)
    result = check.grade(_ctx(), ms)
    d = _details(result)[0]
    assert d.kind == "new"
    assert d.level == "fail"
    assert d.baseline is None
    assert result.passed is False


def test_nonreg_new_scope_ok_above_warn() -> None:
    check = NonRegressionCheck(_CC(), warn=0.5, fail=0.25)
    ms = _ms([_cc("a.py::new", 3)], [])  # score 1.0 >= warn(0.5)
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
