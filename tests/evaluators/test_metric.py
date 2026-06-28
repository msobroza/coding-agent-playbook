"""Tests for the ``Metric`` layer + the builtin/execution metrics.

The ``Metric`` layer is the "measure" leaf of the
``Metric`` -> ``Check`` -> ``Rubric`` stack: each builtin/execution module keeps
its computation in a module-level ``_measure`` function the ``Metric`` calls.
These tests cover registry membership + partition, in-tree precedence over an
entry-point plugin, ``get_metric`` lookup, the radon-absent skip, and
representative measured values.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators import metric as metric_mod
from coding_agent_playbook.evaluators.metric import (
    Metric,
    all_metrics,
    execution_metrics,
    get_metric,
    register_metric,
    static_metrics,
)
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import EvalContext, Measurement

if TYPE_CHECKING:
    from pathlib import Path


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def _static_ctx(source: str, label: str = "t.py") -> EvalContext:
    return EvalContext(module=parse_module(source, label), source=source, label=label)


def _by_scope(measurements: list[Measurement]) -> dict[str, float]:
    return {m.scope_key: m.value for m in measurements}


_STATIC_BUILTIN_NAMES = {
    "cyclomatic_complexity",
    "wmc",
    "lcom4",
    "dit",
    "cbo",
    "maintainability_index",
}
_EXECUTION_NAMES = {"coverage", "test_pass_rate"}


# --------------------------------------------------------------------------- #
# registry membership + partition
# --------------------------------------------------------------------------- #


def test_all_metrics_includes_builtins_and_execution() -> None:
    names = {m.name for m in all_metrics()}
    assert names >= _STATIC_BUILTIN_NAMES
    assert names >= _EXECUTION_NAMES


def test_static_metrics_excludes_execution() -> None:
    names = {m.name for m in static_metrics()}
    assert names >= _STATIC_BUILTIN_NAMES
    assert "coverage" not in names
    assert "test_pass_rate" not in names
    assert all(not m.needs_project for m in static_metrics())


def test_execution_metrics_is_the_needs_project_partition() -> None:
    names = {m.name for m in execution_metrics()}
    assert names >= _EXECUTION_NAMES
    assert all(m.needs_project for m in execution_metrics())
    # The two partitions are disjoint and together cover all metrics.
    static_names = {m.name for m in static_metrics()}
    assert static_names.isdisjoint(names)
    assert static_names | names == {m.name for m in all_metrics()}


def test_get_metric_returns_instance() -> None:
    assert get_metric("cyclomatic_complexity").name == "cyclomatic_complexity"


def test_get_metric_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_metric("does_not_exist")


# --------------------------------------------------------------------------- #
# in-tree precedence over an entry-point plugin
# --------------------------------------------------------------------------- #


class _DummyMetric(Metric):
    name = "_dummy_metric"
    scope = Scope.FUNCTION
    higher_is_worse = True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


def test_entry_point_metric_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    class _PluginMetric(_DummyMetric):
        name = "_plugin_metric"

    class _FakeEntryPoint:
        name = "_plugin_metric"

        def load(self) -> type[Metric]:
            return _PluginMetric

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == "coding_agent_playbook.metrics"
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.metric.metadata.entry_points",
        _fake_entry_points,
    )
    names = {m.name for m in all_metrics()}
    assert "_plugin_metric" in names


def test_entry_point_does_not_override_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plugin reusing a builtin name must not shadow the in-tree builtin."""

    class _Imposter(_DummyMetric):
        name = "cyclomatic_complexity"

    class _FakeEntryPoint:
        name = "cyclomatic_complexity"

        def load(self) -> type[Metric]:
            return _Imposter

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.metric.metadata.entry_points",
        _fake_entry_points,
    )
    matches = [m for m in all_metrics() if m.name == "cyclomatic_complexity"]
    assert len(matches) == 1
    assert not isinstance(matches[0], _Imposter)


def test_register_metric_decorator_adds_to_registry() -> None:
    @register_metric
    class _TempMetric(_DummyMetric):
        name = "_temp_registered_metric"

    try:
        assert get_metric("_temp_registered_metric").name == "_temp_registered_metric"
        assert any(m.name == "_temp_registered_metric" for m in all_metrics())
    finally:
        metric_mod._METRIC_REGISTRY.pop("_temp_registered_metric", None)


# --------------------------------------------------------------------------- #
# representative measured values
# --------------------------------------------------------------------------- #


_HIGH_CC = """
def hot(x):
    if x > 0 and x < 10:
        return 1
    for i in range(x):
        if i:
            while i:
                i -= 1
    try:
        return 1 / x
    except ZeroDivisionError:
        return 0
"""

_CHAIN = """
class A:
    pass
class B(A):
    pass
class C(B):
    pass
"""


def test_cyclomatic_metric_measures_each_function() -> None:
    m = get_metric("cyclomatic_complexity")
    assert m.scope is Scope.FUNCTION
    values = _by_scope(m.measure(_static_ctx(_HIGH_CC)))
    # 1 + if + and + for + if + while + except = 7.
    assert values["t.py::hot"] == 7


def test_dit_metric_measures_inheritance_depth() -> None:
    m = get_metric("dit")
    assert m.scope is Scope.CLASS
    values = _by_scope(m.measure(_static_ctx(_CHAIN)))
    assert values["t.py::A"] == 0
    assert values["t.py::B"] == 1
    assert values["t.py::C"] == 2


def test_static_metric_available_requires_module() -> None:
    m = get_metric("cyclomatic_complexity")
    assert m.available(_static_ctx("def f():\n    return 1\n")) is True
    assert m.available(EvalContext(module=None, source="", label="t.py")) is False


# --------------------------------------------------------------------------- #
# execution metric: coverage / test_pass_rate share the cached project run
# --------------------------------------------------------------------------- #

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


def _exec_ctx(handle: object | None, label: str = "suite") -> EvalContext:
    return EvalContext(module=None, source="", label=label, project=handle)


def test_test_pass_rate_metric_measures_pass_rate(tmp_path: Path) -> None:
    from coding_agent_playbook.evaluators.execution.project import ProjectHandle

    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.py").write_text(_MOD, encoding="utf-8")
    (root / "test_mod.py").write_text(_TEST_PASS, encoding="utf-8")
    handle = ProjectHandle.create(root, tmp_path / "rep")

    m = get_metric("test_pass_rate")
    assert m.needs_project is True
    assert m.available(_exec_ctx(None)) is False
    assert m.available(_exec_ctx(handle)) is True

    ms = m.measure(_exec_ctx(handle))
    assert len(ms) == 1
    assert ms[0].value == 1.0
    assert ms[0].scope_key == "suite"


def test_coverage_metric_measures_per_file_and_total(tmp_path: Path) -> None:
    from coding_agent_playbook.evaluators.execution.project import ProjectHandle

    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.py").write_text(_MOD, encoding="utf-8")
    (root / "test_mod.py").write_text(_TEST_PASS, encoding="utf-8")
    handle = ProjectHandle.create(root, tmp_path / "rep")

    m = get_metric("coverage")
    assert m.needs_project is True
    ms = m.measure(_exec_ctx(handle, label="suite"))
    keys = {meas.scope_key for meas in ms}
    assert "suite" in keys
    assert any(k.endswith("mod.py") for k in keys)


# --------------------------------------------------------------------------- #
# maintainability_index: radon-gated availability
# --------------------------------------------------------------------------- #


def test_maintainability_metric_unavailable_without_radon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When radon is absent, the MI metric's ``available`` is False even with a module."""
    import importlib.util as _ilu

    real_find_spec = _ilu.find_spec

    def _no_radon(name: str, *args: object, **kwargs: object) -> object | None:
        if name == "radon":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.builtins.maintainability.importlib.util.find_spec",
        _no_radon,
    )
    m = get_metric("maintainability_index")
    assert m.requires == "radon"
    ctx = _static_ctx("def f():\n    return 1\n")
    assert m.available(ctx) is False
