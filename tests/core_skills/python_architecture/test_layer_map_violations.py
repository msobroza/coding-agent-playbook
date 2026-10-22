"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill: wrong-way and type-only imports.

Shared trees and run helpers live in ``_scripts.py``; the ``layer_map`` and ``run_map``
fixtures in ``conftest.py`` (prU D2, D25).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.python_architecture._scripts import (
    CLEAN_TREE,
    ORM_VIOLATION,
    ROUTER_IMPORTS_ORM,
    Outcome,
    write_tree,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.catalog


# --- violations ---------------------------------------------------------------------


def test_router_importing_orm_module_is_a_named_violation(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map("--json")
    assert outcome.code == 1
    assert outcome.report()["violations"] == [ORM_VIOLATION]


def test_text_report_names_violation_with_file_and_line(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map()
    assert outcome.code == 1
    assert "Rule violations: 1" in outcome.out
    assert (
        "rentals/routers/bikes.py:3  rentals.routers.bikes [interface] imports "
        "rentals.db.bikes [infrastructure]"
    ) in outcome.out
    assert "interface -> infrastructure: 1  (breaks a rule)" in outcome.out


def test_clean_layered_tree_exits_zero(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert report["cycles"] == []
    assert report["layers"] == {
        "rentals.db": "infrastructure",
        "rentals.db.bikes": "infrastructure",
        "rentals.domain": "domain",
        "rentals.domain.bike": "domain",
        "rentals.routers": "interface",
        "rentals.routers.bikes": "interface",
        "rentals.services": "application",
        "rentals.services.booking": "application",
    }
    assert report["unlayered"] == ["rentals", "rentals.main"]
    assert report["composition_roots"] == ["rentals.main"]


def test_clean_text_report_says_nothing_found(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map()
    assert outcome.code == 0
    assert outcome.out.rstrip().endswith("No rule violations or import cycles found.")
    assert "domain         -> nothing" in outcome.out


def test_flows_count_distinct_module_pairs_in_layer_order(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    returns = """
        from rentals.services.booking import book_bike
        from rentals.services.booking import cancel_booking
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/returns.py": returns})
    assert run_map("--json").report()["flows"] == [
        ["interface", "application", 2],
        ["interface", "domain", 1],
        ["application", "domain", 1],
        ["infrastructure", "application", 1],
        ["infrastructure", "domain", 1],
    ]


def test_function_local_import_still_breaks_a_rule(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    lazy = """
        def list_bikes():
            from rentals.db.bikes import BikeRow
            return BikeRow
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": lazy})
    outcome = run_map("--json")
    assert outcome.code == 1
    assert [v["line"] for v in outcome.report()["violations"]] == [2]


# --- type-only imports --------------------------------------------------------------


def test_type_checking_import_is_type_only_not_a_violation(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        import typing
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from rentals.db.bikes import BikeRow

        if typing.TYPE_CHECKING:
            import rentals.db.bikes
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": router})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert report["type_only"] == [
        {**ORM_VIOLATION, "line": 5},
        {**ORM_VIOLATION, "line": 8},
    ]


def test_else_branch_of_type_checking_runs_and_is_checked(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from rentals.domain.bike import Bike
        else:
            from rentals.db.bikes import BikeRow
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": router})
    outcome = run_map("--json")
    assert outcome.code == 1
    assert outcome.report()["violations"] == [{**ORM_VIOLATION, "line": 6}]
    assert outcome.report()["type_only"] == []
