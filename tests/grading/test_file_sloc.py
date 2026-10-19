"""``file_sloc``: radon raw SLOC, opt-in and regression-exempt (prK §F.2.1).

The measuring cases need radon (the optional extra) and skip without it; the
availability and grading cases do not.
"""

from __future__ import annotations

import importlib.util

import pytest

from coding_agent_playbook.grading.check import MeasurementSet
from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.static_metrics.file_sloc import FileSlocMetric
from coding_agent_playbook.grading.types import (
    AbsoluteThreshold,
    EvalContext,
    Measurement,
    ScopeDetail,
)
from coding_agent_playbook.metrics_gate.config import MetricConfig
from coding_agent_playbook.metrics_gate.policy import metric_check


def _ctx(source: str) -> EvalContext:
    return EvalContext(module=parse_module(source, "a.py"), source=source, label="a.py")


def test_measures_radon_raw_sloc() -> None:
    pytest.importorskip("radon")
    source = "# a comment\nx = 1\n\n\ndef f():\n    return x\n"

    [measured] = FileSlocMetric().measure(_ctx(source))

    assert (measured.evaluator, measured.scope_key, measured.value) == ("file_sloc", "a.py", 3.0)


def test_unavailable_when_find_spec_radon_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name == "radon" else real(name, *a)
    )

    assert not FileSlocMetric().available(_ctx("x = 1\n"))


def _grade(
    candidate: float, baseline: float | None, config: MetricConfig
) -> tuple[ScopeDetail, ...]:
    check = metric_check("file_sloc", config)
    assert check is not None
    measurements = MeasurementSet(
        [Measurement("file_sloc", "a.py", candidate)],
        None if baseline is None else [Measurement("file_sloc", "a.py", baseline)],
    )
    result = check.grade(_ctx("x = 1\n"), measurements)
    return tuple(d for d in result.subresults if isinstance(d, ScopeDetail))


def test_regression_exempt_max_worsening_one() -> None:
    [detail] = _grade(900.0, 100.0, MetricConfig())

    assert (detail.kind, detail.level) == ("regression", "ok")


def test_band_flags_new_600_sloc_file_not_legacy() -> None:
    band = MetricConfig(thresholds={"file_sloc": AbsoluteThreshold(warn=1.0, fail=0.6)})

    [new] = _grade(600.0, None, band)
    [legacy] = _grade(600.0, 590.0, band)

    assert (new.kind, new.level) == ("new", "fail")
    assert (legacy.kind, legacy.level) == ("regression", "ok")
