"""End-to-end normalization goldens for the C3 cutover.

This is the single place that documents, per metric, **the new boundary**: each
builtin/execution metric's :meth:`~coding_agent_playbook.grading.metric.Metric.score`
maps a representative raw value to a ``0-1`` goodness (higher = always better),
and the metric's default ``[metrics]`` policy (:data:`METRIC_DEFAULTS`, now ``0-1``
cutoffs) grades that score into an ``ok|warn|fail`` level via a
:class:`~coding_agent_playbook.grading.check.ThresholdCheck`.

The level rule is strict-below on the normalized score: a scope ``fail``\\ s when
its score is *strictly below* ``fail`` and ``warn``\\ s when *strictly below*
``warn`` (a score landing exactly on a cutoff is the higher level). The named
boundary cases the cutover hinges on:

* ``cyclomatic_complexity`` raw 12.5 -> score 0.5 -> *warn* is NOT triggered
  (0.5 is not < warn=0.5); raw 14 -> 0.4 -> warn; raw 17 -> 0.2 -> fail.
* ``coverage`` raw 80 -> 0.8 sits exactly on warn=0.8 -> ok; raw 79 -> 0.79 -> warn.
* ``maintainability_index`` raw 65 -> 0.65 sits exactly on fail=0.65 -> ok; raw
  64 -> 0.64 -> fail.
* ``test_pass_rate`` raw 0.9 -> 0.9 -> fail (anything below the fail=1.0 floor).
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.grading.check import MeasurementSet, ThresholdCheck
from coding_agent_playbook.grading.metric import Metric, get_metric
from coding_agent_playbook.grading.types import EvalContext, Measurement, ScopeDetail
from coding_agent_playbook.metrics_gate.policy import METRIC_DEFAULTS


def _ctx() -> EvalContext:
    return EvalContext(module=None, source="", label="norm")


def _level(metric: Metric, raw: float) -> str:
    """Grade ``raw`` for ``metric`` under its METRIC_DEFAULTS 0-1 cutoffs."""
    warn, fail, _ = METRIC_DEFAULTS[metric.name]
    check = ThresholdCheck(metric, warn=warn, fail=fail)
    ms = MeasurementSet([Measurement(evaluator=metric.name, scope_key="s", value=raw)])
    result = check.grade(_ctx(), ms)
    (detail,) = result.subresults
    assert isinstance(detail, ScopeDetail)
    # The raw value rides through on .value; the normalized score on .score.
    assert detail.value == raw
    assert detail.score == pytest.approx(metric.score(raw))
    return detail.level


# --------------------------------------------------------------------------- #
# Per-metric: representative score + level under the default cutoff
# --------------------------------------------------------------------------- #


def test_cyclomatic_complexity_normalization() -> None:
    m = get_metric("cyclomatic_complexity")  # RampNormalizer(good=5, bad=20)
    assert m.score(12.5) == pytest.approx(0.5)
    # warn=0.5, fail=0.25: 0.5 is NOT < 0.5 -> ok at the boundary.
    assert _level(m, 12.5) == "ok"
    assert _level(m, 14) == "warn"  # score 0.4
    assert _level(m, 17) == "fail"  # score 0.2
    assert _level(m, 5) == "ok"  # score 1.0


def test_wmc_normalization() -> None:
    m = get_metric("wmc")  # RampNormalizer(good=10, bad=60); default (None, 0.2, 0)
    assert m.score(35) == pytest.approx(0.5)
    assert _level(m, 35) == "ok"  # no warn bound; 0.5 >= fail 0.2
    assert _level(m, 52) == "fail"  # score (60-52)/50 = 0.16 < 0.2
    assert _level(m, 10) == "ok"  # score 1.0


def test_lcom4_normalization() -> None:
    m = get_metric("lcom4")  # RampNormalizer(good=1, bad=6); default (0.5, None, 0)
    assert m.score(3.5) == pytest.approx(0.5)
    # warn=0.5, no fail: 0.5 is not < 0.5 -> ok; below 0.5 -> warn (never fails).
    assert _level(m, 3.5) == "ok"
    assert _level(m, 4) == "warn"  # score (6-4)/5 = 0.4
    assert _level(m, 6) == "warn"  # score 0.0, but no fail bound -> warn


def test_dit_normalization() -> None:
    m = get_metric("dit")  # RampNormalizer(good=1, bad=8); default (0.5, None, 0)
    assert m.score(4.5) == pytest.approx(0.5)
    assert _level(m, 4.5) == "ok"
    assert _level(m, 6) == "warn"  # score (8-6)/7 ~ 0.286 < 0.5, no fail -> warn


def test_cbo_normalization() -> None:
    m = get_metric("cbo")  # RampNormalizer(good=3, bad=25); default (0.5, None, 0)
    assert m.score(14) == pytest.approx(0.5)
    assert _level(m, 14) == "ok"
    assert _level(m, 20) == "warn"  # score (25-20)/22 ~ 0.227 -> warn (no fail)


def test_maintainability_index_normalization() -> None:
    m = get_metric("maintainability_index")  # PercentNormalizer; default (None, 0.65, 0)
    assert m.score(65) == pytest.approx(0.65)
    # fail=0.65: 0.65 is NOT < 0.65 -> ok exactly on the boundary.
    assert _level(m, 65) == "ok"
    assert _level(m, 64) == "fail"  # score 0.64 < 0.65
    assert _level(m, 100) == "ok"  # score 1.0


def test_coverage_normalization() -> None:
    m = get_metric("coverage")  # PercentNormalizer; default (0.8, None, 0)
    assert m.score(80) == pytest.approx(0.8)
    # warn=0.8: 0.8 is NOT < 0.8 -> ok exactly on the old raw-80 boundary.
    assert _level(m, 80) == "ok"
    assert _level(m, 79) == "warn"  # score 0.79 < 0.8 (no fail bound -> warn)
    assert _level(m, 95) == "ok"


def test_test_pass_rate_normalization() -> None:
    m = get_metric("test_pass_rate")  # Identity; default (None, 1.0, 0)
    assert m.score(0.9) == pytest.approx(0.9)
    # fail=1.0: any score below 1.0 fails (every test must pass).
    assert _level(m, 0.9) == "fail"
    assert _level(m, 1.0) == "ok"  # 1.0 is not < 1.0


# --------------------------------------------------------------------------- #
# Direction is fully folded into the normalizer: a higher-is-worse metric and a
# higher-is-better one both expose "1.0 == best", so the Check never branches.
# --------------------------------------------------------------------------- #


def test_direction_is_folded_into_the_normalizer() -> None:
    cc = get_metric("cyclomatic_complexity")  # higher raw is worse
    cov = get_metric("coverage")  # higher raw is better
    # Worse CC -> lower goodness; higher coverage -> higher goodness. Both obey
    # "1.0 is best", so the grading layer compares scores identically.
    assert cc.score(5) > cc.score(15)
    assert cov.score(95) > cov.score(60)
