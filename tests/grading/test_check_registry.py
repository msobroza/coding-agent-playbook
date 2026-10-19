"""Tests for the Check registry — ``grading/check_registry.py``.

The Check registry mirrors the rubric/metric registry idiom, but its values are
**factories** (``Callable[..., Check]``) rather than zero-arg classes, because a
check takes ctor kwargs. :func:`get_check` resolves a factory (builtins first,
then the ``coding_agent_playbook.checks`` entry-point group) and calls it with the
caller's kwargs. The metric-backed factories route through
:func:`_resolve_metric_source`, which takes exactly one of ``metric=`` (a
registered :class:`Metric` name) or ``judge=`` (a criterion wrapped in a
:class:`JudgeMetric`).

This track is additive — nothing in the eval/task pipeline consumes the registry
yet, so these tests exercise it directly.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.checks.files import FileExistsCheck
from coding_agent_playbook.grading.check import NonRegressionCheck, ThresholdCheck
from coding_agent_playbook.grading.check_registry import (
    _resolve_metric_source,
    all_check_ids,
    get_check,
    register_check,
)
from coding_agent_playbook.grading.judge_metric import JudgeMetric


def test_get_check_threshold_over_a_named_metric() -> None:
    check = get_check("threshold", metric="cyclomatic_complexity", fail=0.5)
    assert isinstance(check, ThresholdCheck)
    assert check.metric.name == "cyclomatic_complexity"


def test_get_check_threshold_over_a_judge_criterion() -> None:
    check = get_check("threshold", judge="clear naming", fail=0.5)
    assert isinstance(check, ThresholdCheck)
    assert isinstance(check.metric, JudgeMetric)
    assert check.metric.name == "judge:clear-naming"


def test_get_check_non_regression_over_a_named_metric() -> None:
    check = get_check("non_regression", metric="coverage", max_worsening=0.0)
    assert isinstance(check, NonRegressionCheck)
    assert check.metric.name == "coverage"


def test_resolve_metric_source_metric_only() -> None:
    metric = _resolve_metric_source("cyclomatic_complexity", None)
    assert metric.name == "cyclomatic_complexity"


def test_resolve_metric_source_judge_only() -> None:
    metric = _resolve_metric_source(None, "clear naming")
    assert isinstance(metric, JudgeMetric)
    assert metric.name == "judge:clear-naming"


def test_resolve_metric_source_both_raises() -> None:
    with pytest.raises(ValueError):
        _resolve_metric_source("cyclomatic_complexity", "clear naming")


def test_resolve_metric_source_neither_raises() -> None:
    with pytest.raises(ValueError):
        _resolve_metric_source(None, None)


def test_get_check_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_check("nope")


def test_all_check_ids_membership() -> None:
    ids = all_check_ids()
    for expected in (
        "threshold",
        "non_regression",
        "tests_pass",
        "coverage",
    ):
        assert expected in ids


def test_entry_point_check_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = FileExistsCheck("from-plugin.py")

    def _plugin_factory(**_kwargs: object) -> FileExistsCheck:
        return sentinel

    class _FakeEntryPoint:
        name = "_plugin_check"

        def load(self) -> object:
            return _plugin_factory

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.grading.check_registry.metadata.entry_points",
        _fake_entry_points,
    )
    assert "_plugin_check" in all_check_ids()
    assert get_check("_plugin_check") is sentinel


def test_register_check_registers_a_factory() -> None:
    import coding_agent_playbook.grading.check_registry as registry_mod

    @register_check("_test_custom_check")
    def _factory(**_kwargs: object) -> FileExistsCheck:
        return FileExistsCheck("custom.py")

    try:
        assert "_test_custom_check" in all_check_ids()
        check = get_check("_test_custom_check")
        assert isinstance(check, FileExistsCheck)
        assert check.path == "custom.py"
    finally:
        registry_mod._CHECK_REGISTRY.pop("_test_custom_check", None)
