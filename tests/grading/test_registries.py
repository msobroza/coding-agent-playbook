"""The in-tree Metric and Check registries keep their contents across the grading rename.

The package ``__init__`` files hold only a docstring (ADR 0002), so importing a
package no longer fires the ``@register_metric`` / ``@register_check`` decorators
of its modules: ``grading/metric.py`` and ``grading/check_registry.py`` import their
in-tree modules by explicit list instead. The baselines below are what the
kernel registered before the rename, when each package ``__init__`` imported its
modules, read from a fresh interpreter (specs/prT-package-layout.md 7.4 N25).
"""

from __future__ import annotations

import ast
from typing import Final

import pytest

from coding_agent_playbook.grading.check_registry import all_check_ids
from coding_agent_playbook.grading.execution_metrics import diff_coverage
from coding_agent_playbook.grading.metric import all_metrics
from coding_agent_playbook.grading.static_metrics import ruff_violations
from tests.engine_modules import engine_module
from tests.import_probe import run_python_probe

#: The 12 in-tree metrics: 9 static, then test_pass_rate, coverage and diff_coverage.
_BASELINE_METRIC_NAMES: Final = [
    "cbo",
    "coverage",
    "cyclomatic_complexity",
    "diff_coverage",
    "dit",
    "docstring_example",
    "file_sloc",
    "lcom4",
    "maintainability_index",
    "ruff_violations",
    "test_pass_rate",
    "wmc",
]
#: The kernel's check ids; the eval-only families register from evals.compile._handles.
_BASELINE_CHECK_IDS: Final = ["coverage", "non_regression", "tests_pass", "threshold"]
#: The order ``static_metrics()`` and ``execution_metrics()`` listed before the rename,
#: whichever module of a family was imported first: a family's package ``__init__``
#: imported all of its modules in this order.
_BASELINE_STATIC_ORDER: Final = [
    "cbo",
    "cyclomatic_complexity",
    "dit",
    "docstring_example",
    "file_sloc",
    "lcom4",
    "maintainability_index",
    "ruff_violations",
    "wmc",
]
_BASELINE_EXECUTION_ORDER: Final = ["coverage", "diff_coverage", "test_pass_rate"]
#: The order ``all_check_ids()`` listed the kernel's ids before the rename, ahead of the
#: eval-only families whichever check module was imported first.
_BASELINE_KERNEL_CHECK_ORDER: Final = ["threshold", "non_regression", "tests_pass", "coverage"]
#: The eval handle builder, whose import registers the eval-only check families.
_EVAL_HANDLE_BUILDER: Final = engine_module("coding_agent_playbook.evals.compile._handles")


def test_metric_and_check_registries_are_unchanged() -> None:
    """A fresh interpreter that imports only the two registries sees every in-tree builtin.

    In this process other tests have already imported the metric and check modules,
    which would hide a module the explicit lists leave out.
    """
    probe = (
        f"from {all_metrics.__module__} import all_metrics; "
        f"from {all_check_ids.__module__} import all_check_ids; "
        "print([sorted(m.name for m in all_metrics()), sorted(all_check_ids())])"
    )

    names, ids = ast.literal_eval(run_python_probe(probe))

    assert (names, ids) == (_BASELINE_METRIC_NAMES, _BASELINE_CHECK_IDS)


def test_builtin_metrics_keep_their_order_whichever_module_loads_first() -> None:
    """The gate's checks keep their order when a metric module is imported early.

    ``metrics_gate.suite`` imports ``diff_coverage`` before the registry loads, and the
    Stop handlers import ``ruff_violations``; the gate builds its rubric in this order.
    """
    probe = (
        f"import {ruff_violations.__name__}, {diff_coverage.__name__}; "
        f"from {all_metrics.__module__} import execution_metrics, static_metrics; "
        "print([[m.name for m in static_metrics()], [m.name for m in execution_metrics()]])"
    )

    static, execution = ast.literal_eval(run_python_probe(probe))

    assert (static, execution) == (_BASELINE_STATIC_ORDER, _BASELINE_EXECUTION_ORDER)


#: Registers a metric from outside the builtin modules, as an out-of-tree author would.
_REGISTER_LATE: Final = (
    f"from {all_metrics.__module__} import Metric, register_metric; "
    "register_metric(type('Late', (Metric,), {'name': 'late', 'measure': lambda s, c: []}))"
)
_IMPORT_DIFF_COVERAGE: Final = f"import {diff_coverage.__name__}"


@pytest.mark.parametrize(
    ("preamble", "expected"),
    [
        pytest.param(
            [_REGISTER_LATE],
            ["late", *_BASELINE_STATIC_ORDER, *_BASELINE_EXECUTION_ORDER],
            id="metric-registered-before-the-builtins",
        ),
        pytest.param(
            [_IMPORT_DIFF_COVERAGE],
            [*_BASELINE_EXECUTION_ORDER, *_BASELINE_STATIC_ORDER],
            id="execution-family-imported-first",
        ),
        pytest.param(
            [_IMPORT_DIFF_COVERAGE, _REGISTER_LATE],
            [*_BASELINE_EXECUTION_ORDER, "late", *_BASELINE_STATIC_ORDER],
            id="execution-family-then-a-metric",
        ),
    ],
)
def test_all_metrics_lists_each_builtin_family_where_its_first_module_registered(
    preamble: list[str], expected: list[str]
) -> None:
    """``all_metrics()`` keeps the order it had when a package ``__init__`` registered a family.

    Importing any module of a family registered the whole family as one block, in
    its package ``__init__`` order; a metric registered elsewhere kept its own place.
    """
    probe = "; ".join(
        [
            *preamble,
            f"from {all_metrics.__module__} import all_metrics",
            "print([m.name for m in all_metrics()])",
        ]
    )

    names = ast.literal_eval(run_python_probe(probe))

    assert names == expected


def test_kernel_check_ids_list_first_when_the_eval_families_load_first() -> None:
    """``all_check_ids()`` lists the kernel's ids first even when an eval family loads first.

    Importing the check registry used to register the execution checks right after
    ``threshold`` and ``non_regression``, before any eval family could.
    """
    probe = (
        f"import {_EVAL_HANDLE_BUILDER}; "
        f"from {all_check_ids.__module__} import all_check_ids; "
        "print(all_check_ids())"
    )

    ids = ast.literal_eval(run_python_probe(probe))

    assert ids[: len(_BASELINE_KERNEL_CHECK_ORDER)] == _BASELINE_KERNEL_CHECK_ORDER
