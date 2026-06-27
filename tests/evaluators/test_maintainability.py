"""Tests for the radon-backed maintainability_index evaluator (SPEC prM §B, M2).

Two paths:

* **present** - when ``radon`` is installed, the evaluator yields a single
  FILE-scope :class:`Measurement` whose value is a float in ``(0, 100]`` and a
  long/complex file scores lower than a trivial one. These tests are skipped via
  :func:`pytest.importorskip` when radon is absent.
* **absent** - with ``importlib.util.find_spec`` monkeypatched to report radon
  missing, ``available()`` is ``False`` (so the gate skips it) and the engine
  still imports/enumerates every evaluator without radon installed.
"""

from __future__ import annotations

import importlib.util

import pytest

from coding_agent_playbook.evaluators.builtins.maintainability import MaintainabilityIndex
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.registry import all_evaluators, get_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
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


def test_maintainability_defaults() -> None:
    ev = MaintainabilityIndex()
    assert ev.name == "maintainability_index"
    assert ev.scope is Scope.FILE
    assert ev.value_kind is ValueKind.NUMERIC
    assert ev.determinism is Determinism.DETERMINISTIC
    assert ev.higher_is_worse is False
    assert ev.requires == "radon"
    assert ev.default_absolute.fail == 65.0
    assert ev.default_regression.max_worsening == 0.0


def test_maintainability_is_registered() -> None:
    ev = get_evaluator("maintainability_index")
    assert ev.name == "maintainability_index"
    assert ev.higher_is_worse is False
    assert "maintainability_index" in {e.name for e in all_evaluators()}


# --- present path (radon installed) -----------------------------------------


def test_maintainability_value_is_float_in_range() -> None:
    pytest.importorskip("radon")
    ev = get_evaluator("maintainability_index")
    measurements = ev.evaluate(_ctx(_TRIVIAL))
    assert len(measurements) == 1
    m = measurements[0]
    assert isinstance(m, Measurement)
    assert m.evaluator == "maintainability_index"
    # FILE scope => one measurement keyed by the bare label.
    assert m.scope_key == "t.py"
    assert isinstance(m.value, float)
    assert 0.0 < m.value <= 100.0


def test_maintainability_complex_scores_lower_than_trivial() -> None:
    pytest.importorskip("radon")
    ev = get_evaluator("maintainability_index")
    trivial = ev.evaluate(_ctx(_TRIVIAL))[0].value
    complex_ = ev.evaluate(_ctx(_COMPLEX))[0].value
    assert complex_ < trivial


def test_maintainability_handles_blank_source() -> None:
    pytest.importorskip("radon")
    ev = get_evaluator("maintainability_index")
    measurements = ev.evaluate(_ctx("\n   \n"))
    assert len(measurements) == 1
    assert isinstance(measurements[0].value, float)


def test_maintainability_available_true_when_radon_present() -> None:
    pytest.importorskip("radon")
    ev = MaintainabilityIndex()
    assert ev.available(_ctx(_TRIVIAL)) is True


def test_maintainability_evaluate_without_module_is_empty() -> None:
    # Defensive guard (parity with the ast builtins): no parsed module => no
    # measurement, and radon is never imported. Works with or without radon.
    ev = MaintainabilityIndex()
    ctx = EvalContext(module=None, source="x", label="t.py")
    assert ev.evaluate(ctx) == []


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
    ev = MaintainabilityIndex()
    assert ev.available(_ctx(_TRIVIAL)) is False


def test_engine_enumerates_evaluators_without_radon(
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
    names = {ev.name for ev in all_evaluators()}
    assert "maintainability_index" in names
    ev = get_evaluator("maintainability_index")
    ctx = EvalContext(module=parse_module(_TRIVIAL, "t.py"), source=_TRIVIAL, label="t.py")
    assert ev.available(ctx) is False
