"""Tests for the Evaluator ABC, registry, and to_score ramp (SPEC prM §A)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators import registry as registry_mod
from coding_agent_playbook.evaluators.registry import (
    Evaluator,
    all_evaluators,
    deterministic_evaluators,
    get_evaluator,
    register_evaluator,
    static_evaluators,
)
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
    ResolvedPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext


class _DummyHigherWorse(Evaluator):
    name = "_dummy_higher_worse"
    scope = Scope.FUNCTION
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    default_absolute = AbsoluteThreshold(warn=10, fail=20)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        return []


def _ramp_policy() -> ResolvedPolicy:
    return ResolvedPolicy(
        absolute=AbsoluteThreshold(warn=10, fail=20),
        regression=RegressionPolicy(),
        weight=0.0,
    )


def test_to_score_ramp_higher_is_worse() -> None:
    ev = _DummyHigherWorse()
    policy = _ramp_policy()
    assert ev.to_score(5, policy) == 1.0  # at/under warn => best
    assert ev.to_score(10, policy) == 1.0  # exactly warn => still best
    assert ev.to_score(20, policy) == 0.0  # at/over fail => worst
    assert ev.to_score(25, policy) == 0.0  # over fail clamps
    assert ev.to_score(15, policy) == pytest.approx(0.5)  # midpoint


def test_to_score_ramp_inverted_for_higher_is_better() -> None:
    class _Inverted(_DummyHigherWorse):
        name = "_inverted"
        higher_is_worse = False  # e.g. coverage / MI: higher is better

    ev = _Inverted()
    # warn=10 is the "good" floor, fail=20 the "bad"... inverted: higher value better.
    policy = ResolvedPolicy(
        absolute=AbsoluteThreshold(warn=80, fail=60),
        regression=RegressionPolicy(),
        weight=0.0,
    )
    assert ev.to_score(80, policy) == 1.0  # at/over warn (good) => best
    assert ev.to_score(90, policy) == 1.0  # better than warn clamps to 1
    assert ev.to_score(60, policy) == 0.0  # at/under fail => worst
    assert ev.to_score(70, policy) == pytest.approx(0.5)


def test_to_score_identity_for_score_kind() -> None:
    class _ScoreEv(_DummyHigherWorse):
        name = "_score_ev"
        value_kind = ValueKind.SCORE
        higher_is_worse = False

    ev = _ScoreEv()
    policy = _ramp_policy()
    assert ev.to_score(0.42, policy) == pytest.approx(0.42)
    assert ev.to_score(1.0, policy) == 1.0
    assert ev.to_score(0.0, policy) == 0.0


def test_to_score_identity_for_bool_kind() -> None:
    class _BoolEv(_DummyHigherWorse):
        name = "_bool_ev"
        value_kind = ValueKind.BOOL
        higher_is_worse = False

    ev = _BoolEv()
    policy = _ramp_policy()
    assert ev.to_score(1, policy) == 1.0
    assert ev.to_score(0, policy) == 0.0


def test_to_score_no_bounds_returns_one() -> None:
    ev = _DummyHigherWorse()
    policy = ResolvedPolicy(
        absolute=AbsoluteThreshold(),  # no warn/fail
        regression=RegressionPolicy(),
        weight=0.0,
    )
    assert ev.to_score(99, policy) == 1.0


def test_available_true_for_static_with_module() -> None:
    from coding_agent_playbook.evaluators.parse import parse_module
    from coding_agent_playbook.evaluators.types import EvalContext

    ev = _DummyHigherWorse()
    model = parse_module("def f():\n    return 1\n", "f.py")
    ctx = EvalContext(module=model, source="x", label="f.py")
    assert ev.available(ctx) is True


def test_available_false_without_module() -> None:
    from coding_agent_playbook.evaluators.types import EvalContext

    ev = _DummyHigherWorse()
    ctx = EvalContext(module=None, source="x", label="f.py")
    assert ev.available(ctx) is False


def test_builtins_are_registered() -> None:
    names = {ev.name for ev in all_evaluators()}
    assert {"cyclomatic_complexity", "wmc", "lcom4", "dit", "cbo"} <= names


def test_get_evaluator_returns_instance() -> None:
    ev = get_evaluator("cyclomatic_complexity")
    assert ev.name == "cyclomatic_complexity"


def test_get_evaluator_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_evaluator("does_not_exist")


def test_static_evaluators_filters_to_static() -> None:
    statics = static_evaluators()
    assert all(ev.requires is None or ev.requires == "radon" for ev in statics)
    assert all(not ev.needs_project for ev in statics)
    assert {"cyclomatic_complexity", "wmc"} <= {ev.name for ev in statics}


def test_static_evaluators_excludes_execution() -> None:
    """The execution evaluators (``needs_project=True``) are NOT static even
    though they are DETERMINISTIC + FILE/MODULE scope (carried-forward M1 fix)."""
    names = {ev.name for ev in static_evaluators()}
    assert "coverage" not in names
    assert "test_pass_rate" not in names


def test_deterministic_evaluators_includes_execution() -> None:
    """``deterministic_evaluators()`` spans static *and* execution metrics."""
    dets = deterministic_evaluators()
    assert all(ev.determinism is Determinism.DETERMINISTIC for ev in dets)
    names = {ev.name for ev in dets}
    assert {"coverage", "test_pass_rate"} <= names


def test_needs_project_defaults_false() -> None:
    """Static builtins never need a project handle."""
    assert all(not ev.needs_project for ev in static_evaluators())


def test_deterministic_evaluators_excludes_judged() -> None:
    dets = deterministic_evaluators()
    assert all(ev.determinism is Determinism.DETERMINISTIC for ev in dets)


def test_register_evaluator_decorator_adds_to_registry() -> None:
    @register_evaluator
    class _TempEv(_DummyHigherWorse):
        name = "_temp_registered"

    try:
        assert get_evaluator("_temp_registered").name == "_temp_registered"
        assert any(ev.name == "_temp_registered" for ev in all_evaluators())
    finally:
        registry_mod._REGISTRY.pop("_temp_registered", None)


def test_entry_point_evaluator_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    class _PluginEv(_DummyHigherWorse):
        name = "_plugin_ev"

    class _FakeEntryPoint:
        name = "_plugin_ev"

        def load(self) -> type[Evaluator]:
            return _PluginEv

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == "coding_agent_playbook.evaluators"
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.registry.metadata.entry_points",
        _fake_entry_points,
    )
    try:
        names = {ev.name for ev in all_evaluators()}
        assert "_plugin_ev" in names
    finally:
        registry_mod._REGISTRY.pop("_plugin_ev", None)


def test_entry_point_does_not_override_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plugin reusing a builtin name must not shadow the in-tree builtin."""

    class _Imposter(_DummyHigherWorse):
        name = "cyclomatic_complexity"

    class _FakeEntryPoint:
        name = "cyclomatic_complexity"

        def load(self) -> type[Evaluator]:
            return _Imposter

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.registry.metadata.entry_points",
        _fake_entry_points,
    )
    evs = [ev for ev in all_evaluators() if ev.name == "cyclomatic_complexity"]
    assert len(evs) == 1
    assert not isinstance(evs[0], _Imposter)
