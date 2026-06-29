"""Tests for the radon-backed maintainability_index metric (SPEC prM §B, M2).

Two paths:

* **present** - when ``radon`` is installed, the metric yields a single
  FILE-scope :class:`Measurement` whose value is a float in ``(0, 100]`` and a
  long/complex file scores lower than a trivial one. These tests are skipped via
  :func:`pytest.importorskip` when radon is absent.
* **absent** - with ``importlib.util.find_spec`` monkeypatched to report radon
  missing, ``available()`` is ``False`` (so the gate skips it) and the engine
  still imports/enumerates every metric without radon installed.
"""

from __future__ import annotations

import importlib.util

import pytest

from coding_agent_playbook.evaluators.builtins.maintainability import MaintainabilityIndexMetric
from coding_agent_playbook.evaluators.metric import all_metrics, get_metric
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import EvalContext, Measurement

_TRIVIAL = "def f():\n    return 1\n"

_COMPLEX = """
def tangled(items, flag, mode):
    total = 0
    for i in items:
        if i > 0 and i < 100:
            for j in range(i):
                if j % 2 == 0:
                    total += j
                elif j % 3 == 0:
                    total -= j
                else:
                    total += 1
        elif flag:
            while i > 0:
                i -= 1
                total += i
        else:
            try:
                total += 1 / i
            except ZeroDivisionError:
                total += 0
    if mode == "x":
        return total
    if mode == "y":
        return -total
    return total * 2
"""


def _ctx(source: str, label: str = "t.py") -> EvalContext:
    return EvalContext(module=parse_module(source, label), source=source, label=label)


def test_maintainability_descriptors() -> None:
    m = MaintainabilityIndexMetric()
    assert m.name == "maintainability_index"
    assert m.scope is Scope.FILE
    # PercentNormalizer: 0-100 MI -> 0-1 goodness (65 -> 0.65).
    assert m.score(100) == 1.0
    assert m.score(65) == pytest.approx(0.65)
    assert m.score(0) == 0.0
    assert m.requires == "radon"


def test_maintainability_is_registered() -> None:
    m = get_metric("maintainability_index")
    assert m.name == "maintainability_index"
    assert m.score(65) == pytest.approx(0.65)
    assert "maintainability_index" in {x.name for x in all_metrics()}


# --- present path (radon installed) -----------------------------------------


def test_maintainability_value_is_float_in_range() -> None:
    pytest.importorskip("radon")
    m = get_metric("maintainability_index")
    measurements = m.measure(_ctx(_TRIVIAL))
    assert len(measurements) == 1
    meas = measurements[0]
    assert isinstance(meas, Measurement)
    assert meas.evaluator == "maintainability_index"
    # FILE scope => one measurement keyed by the bare label.
    assert meas.scope_key == "t.py"
    assert isinstance(meas.value, float)
    assert 0.0 < meas.value <= 100.0


def test_maintainability_complex_scores_lower_than_trivial() -> None:
    pytest.importorskip("radon")
    m = get_metric("maintainability_index")
    trivial = m.measure(_ctx(_TRIVIAL))[0].value
    complex_ = m.measure(_ctx(_COMPLEX))[0].value
    assert complex_ < trivial


def test_maintainability_handles_blank_source() -> None:
    pytest.importorskip("radon")
    m = get_metric("maintainability_index")
    measurements = m.measure(_ctx("\n   \n"))
    assert len(measurements) == 1
    assert isinstance(measurements[0].value, float)


def test_maintainability_available_true_when_radon_present() -> None:
    pytest.importorskip("radon")
    m = MaintainabilityIndexMetric()
    assert m.available(_ctx(_TRIVIAL)) is True


def test_maintainability_measure_without_module_is_empty() -> None:
    # Defensive guard (parity with the ast builtins): no parsed module => no
    # measurement, and radon is never imported. Works with or without radon.
    m = MaintainabilityIndexMetric()
    ctx = EvalContext(module=None, source="x", label="t.py")
    assert m.measure(ctx) == []


# --- absent path (radon not importable) -------------------------------------


def test_maintainability_available_false_without_radon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "radon":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    m = MaintainabilityIndexMetric()
    assert m.available(_ctx(_TRIVIAL)) is False


def test_engine_enumerates_metrics_without_radon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "radon":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    # The whole registry still loads; maintainability_index is present but
    # reports unavailable, so the gate simply skips it.
    names = {m.name for m in all_metrics()}
    assert "maintainability_index" in names
    m = get_metric("maintainability_index")
    ctx = EvalContext(module=parse_module(_TRIVIAL, "t.py"), source=_TRIVIAL, label="t.py")
    assert m.available(ctx) is False
