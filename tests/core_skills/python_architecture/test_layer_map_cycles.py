"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill: import cycles.

Shared trees and run helpers live in ``_scripts.py``; the ``layer_map`` and ``run_map``
fixtures in ``conftest.py`` (prU D2, D25).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.python_architecture._scripts import (
    CYCLE_TREE,
    Outcome,
    write_tree,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog


# --- cycles -------------------------------------------------------------------------


def test_import_cycle_between_two_modules_fails_and_is_listed(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, CYCLE_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["violations"] == []
    assert report["cycles"] == [["rentals.services.discounts", "rentals.services.pricing"]]


def test_text_report_lists_the_cycle(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    write_tree(tmp_path, CYCLE_TREE)
    outcome = run_map()
    assert outcome.code == 1
    assert "  rentals.services.discounts, rentals.services.pricing" in outcome.out
    assert "Found 0 rule violations and 1 import cycle." in outcome.out


@pytest.mark.parametrize(
    "discounts",
    [
        "import sys\nif sys.version_info >= (3, 10):\n    import rentals.services.pricing\n",
        "try:\n    from rentals.services.pricing import *\nexcept ImportError:\n    pass\n",
        "class Rules:\n    from rentals.services import pricing\n",
    ],
    ids=["plain-if", "star-import-in-try", "class-body"],
)
def test_module_level_imports_inside_blocks_still_form_cycles(
    tmp_path: Path, run_map: Callable[..., Outcome], discounts: str
) -> None:
    write_tree(tmp_path, {**CYCLE_TREE, "rentals/services/discounts.py": discounts})
    outcome = run_map("--json")
    assert outcome.code == 1
    assert outcome.report()["cycles"] == [
        ["rentals.services.discounts", "rentals.services.pricing"]
    ]


@pytest.mark.parametrize(
    "discounts",
    [
        "def load():\n    import rentals.services.pricing\n",
        "async def load():\n    import rentals.services.pricing\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import rentals.services.pricing\n",
    ],
    ids=["deferred", "deferred-async", "type-only"],
)
def test_deferred_and_type_only_imports_do_not_form_cycles(
    tmp_path: Path, run_map: Callable[..., Outcome], discounts: str
) -> None:
    write_tree(tmp_path, {**CYCLE_TREE, "rentals/services/discounts.py": discounts})
    outcome = run_map("--json")
    assert outcome.code == 0
    assert outcome.report()["cycles"] == []


def test_find_cycles_groups_each_strongly_connected_set(layer_map: ModuleType) -> None:
    graph = {
        "a": {"b"},
        "b": {"c"},
        "c": {"a", "x"},
        "x": {"y"},
        "y": {"x"},
        "z": {"a"},
    }
    assert layer_map.find_cycles(graph) == (("a", "b", "c"), ("x", "y"))
