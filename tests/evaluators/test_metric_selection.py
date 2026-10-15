"""Ruff-shaped metric selection (specs/prK-hook-pack.md §F.0.3 item 2).

:func:`resolve_metric_selection` is pure over the metric list it is handed, so
these tests build that list from the real registry plus named fakes standing in
for the opt-in metrics later steps register (``ruff_violations``,
``file_sloc``). The default selection must stay exactly today's gated set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.metric import (
    Metric,
    all_metrics,
    execution_metrics,
    static_metrics,
)
from coding_agent_playbook.evaluators.normalizer import Identity
from coding_agent_playbook.evaluators.policy import (
    METRIC_FAMILIES,
    OPT_IN_METRICS,
    resolve_metric_selection,
)
from coding_agent_playbook.evaluators.scope import Scope

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext, Measurement


@dataclass
class FakeOptInMetric(Metric):
    """A static metric registered under an opt-in name; it measures nothing."""

    name: str = "ruff_violations"
    scope = Scope.FILE
    normalizer = Identity()

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


def _available() -> list[Metric]:
    """Today's registry plus two opt-in stand-ins, static first, execution last."""
    opt_ins: list[Metric] = [FakeOptInMetric("ruff_violations"), FakeOptInMetric("file_sloc")]
    return [*static_metrics(), *opt_ins, *execution_metrics()]


def _names(metrics: list[Metric]) -> list[str]:
    return [metric.name for metric in metrics]


def _static_names() -> list[str]:
    return _names(static_metrics())


def test_default_selection_equals_static_minus_opt_ins() -> None:
    assert _names(resolve_metric_selection(_available())) == _static_names()


def test_run_tests_appends_execution_metrics() -> None:
    chosen = resolve_metric_selection(_available(), run_tests=True)

    assert _names(chosen) == [*_static_names(), *_names(execution_metrics())]


def test_select_replaces_default() -> None:
    chosen = resolve_metric_selection(_available(), select=["cyclomatic_complexity", "wmc"])

    assert _names(chosen) == ["cyclomatic_complexity", "wmc"]


def test_extend_select_enables_opt_in_only_by_name() -> None:
    by_family = resolve_metric_selection(_available(), extend_select=["quality"])
    by_name = resolve_metric_selection(_available(), extend_select=["ruff_violations"])

    assert "ruff_violations" not in _names(by_family)
    assert _names(by_name) == [*_static_names(), "ruff_violations"]


def test_family_expands_to_non_opt_in_members() -> None:
    chosen = resolve_metric_selection(_available(), select=["quality"])

    expected = [n for n in METRIC_FAMILIES["quality"] if n not in OPT_IN_METRICS]
    assert sorted(_names(chosen)) == sorted(n for n in expected if n in _static_names())


def test_select_testing_family_with_run_tests_picks_execution_metrics() -> None:
    chosen = resolve_metric_selection(_available(), select=["testing"], run_tests=True)

    assert _names(chosen) == _names(execution_metrics())


@pytest.mark.parametrize(
    ("ignore", "removed"),
    [
        (["wmc"], {"wmc"}),
        (["quality"], set(METRIC_FAMILIES["quality"])),
        (["docstrings"], {"ruff_violations"}),  # a family ignore removes its opt-ins too
    ],
    ids=["metric", "family", "opt-in-family"],
)
def test_ignore_removes_metric_and_family(ignore: list[str], removed: set[str]) -> None:
    chosen = resolve_metric_selection(
        _available(), extend_select=["ruff_violations"], ignore=ignore
    )

    assert removed.isdisjoint(_names(chosen))
    kept = [n for n in [*_static_names(), "ruff_violations"] if n not in removed]
    assert _names(chosen) == kept


@pytest.mark.parametrize("field", ["select", "extend_select", "ignore"])
def test_unknown_name_raises_value_error_naming_it(field: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        resolve_metric_selection(_available(), **{field: ["wmc", "complexity"]})  # type: ignore[arg-type]

    message = str(excinfo.value)
    assert message.startswith("unknown metric or family 'complexity'; expected one of: ")
    assert "cyclomatic_complexity" in message
    assert "quality" in message


@pytest.mark.parametrize(
    "kwargs",
    [{"select": ["coverage"]}, {"extend_select": ["testing"]}],
    ids=["by-name", "by-family"],
)
def test_execution_metric_without_run_tests_raises(kwargs: dict[str, list[str]]) -> None:
    with pytest.raises(ValueError) as excinfo:
        resolve_metric_selection(_available(), **kwargs)  # type: ignore[arg-type]

    assert "selected without --run-tests" in str(excinfo.value)
    assert "coverage" in str(excinfo.value)


def test_unregistered_family_member_is_skipped_silently() -> None:
    """``docstring_example`` is a family member no step has registered yet."""
    chosen = resolve_metric_selection(static_metrics(), select=["docstring_example", "wmc"])

    assert _names(chosen) == ["wmc"]


def test_selection_keeps_the_available_order() -> None:
    chosen = resolve_metric_selection(_available(), select=["wmc", "cyclomatic_complexity"])

    assert _names(chosen) == ["cyclomatic_complexity", "wmc"]


def test_family_and_metric_names_are_disjoint() -> None:
    members = {name for family in METRIC_FAMILIES.values() for name in family}
    registered = {metric.name for metric in all_metrics()}

    assert set(METRIC_FAMILIES).isdisjoint(members | registered | OPT_IN_METRICS)
    assert members >= OPT_IN_METRICS
