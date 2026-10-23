"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill: composition roots and their importers.

Shared trees and run helpers live in ``_scripts.py``; the ``layer_map`` and ``run_map``
fixtures in ``conftest.py`` (prU D2, D25).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.python_architecture._scripts import (
    CLEAN_TREE,
    ROOT_FILE_NAMES,
    Outcome,
    write_tree,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.catalog


# --- composition roots --------------------------------------------------------------


@pytest.mark.parametrize("filename", ROOT_FILE_NAMES)
def test_composition_root_files_may_import_any_layer(
    tmp_path: Path, run_map: Callable[..., Outcome], filename: str
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path, {**CLEAN_TREE, f"rentals/routers/{filename}": wiring})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert f"rentals.routers.{filename.removesuffix('.py')}" in report["composition_roots"]
    # A root keeps its directory's layer for the modules that import it.
    assert report["layers"][f"rentals.routers.{filename.removesuffix('.py')}"] == "interface"


@pytest.mark.parametrize(
    "flag_value",
    ["rentals.routers.setup", "routers.setup", "setup", "rentals/routers/setup.py"],
)
def test_root_module_flag_adds_a_composition_root(
    tmp_path: Path, run_map: Callable[..., Outcome], flag_value: str
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/setup.py": wiring})
    assert run_map("--json").code == 1
    outcome = run_map(".", "--root-module", flag_value, "--json")
    assert outcome.code == 0
    assert outcome.report()["composition_roots"] == ["rentals.main", "rentals.routers.setup"]


def test_root_imports_are_left_out_of_flows(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/deps.py": wiring})
    flows = run_map("--json").report()["flows"]
    assert ["interface", "infrastructure", 1] not in flows


@pytest.mark.parametrize(
    "flag_value",
    [
        "src/rentals/routers/setup.py",
        "./src/rentals/routers/setup.py",
        "rentals/routers/setup.py",
        "ABSOLUTE",
    ],
)
def test_root_module_accepts_the_file_path_the_report_prints(
    tmp_path: Path, run_map: Callable[..., Outcome], flag_value: str
) -> None:
    # Regression: in a src layout the printed `file` is src/..., which used to match
    # nothing and leave the wiring module's imports reported as violations.
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path / "src", {**CLEAN_TREE, "rentals/routers/setup.py": wiring})
    printed = run_map("--json").report()["violations"][0]["file"]
    assert printed == "src/rentals/routers/setup.py"
    value = str(tmp_path / printed) if flag_value == "ABSOLUTE" else flag_value
    outcome = run_map(".", "--root-module", value, "--json")
    assert outcome.code == 0, outcome.err
    assert outcome.report()["composition_roots"] == ["rentals.main", "rentals.routers.setup"]


def test_root_module_path_is_also_read_relative_to_root(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path / "proj" / "src", {**CLEAN_TREE, "rentals/routers/setup.py": wiring})
    for value in ("src/rentals/routers/setup.py", "proj/src/rentals/routers/setup.py"):
        outcome = run_map("proj", "--root-module", value, "--json")
        assert outcome.code == 0, (value, outcome.err)
        assert "rentals.routers.setup" in outcome.report()["composition_roots"]


@pytest.mark.parametrize(
    "flag_value", ["nowhere", "rentals.routers.nowhere", "src/rentals/routers/nowhere.py"]
)
def test_root_module_matching_no_scanned_module_is_a_usage_error(
    tmp_path: Path, run_map: Callable[..., Outcome], flag_value: str
) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map(".", "--root-module", flag_value, "--json")
    assert outcome.code == 2
    assert outcome.out == ""
    assert flag_value in outcome.err
    assert "matches no scanned module" in outcome.err


# --- imports of composition roots ---------------------------------------------------


def test_non_interface_code_importing_a_composition_root_is_a_violation(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: a top-level deps.py has no layer, so a use case reaching into it for
    # a session (a service locator) was never checked.
    booking = """
        def book_bike():
            from rentals.deps import get_session
            return get_session()
        """
    files = {
        **CLEAN_TREE,
        "rentals/deps.py": "from rentals.db.bikes import SqlBikeStore\n",
        "rentals/services/booking.py": booking,
        "rentals/domain/bike.py": "import rentals.main\n",
        "rentals/db/bikes.py": "from rentals import deps\n",
    }
    write_tree(tmp_path, files)
    outcome = run_map("--json")
    assert outcome.code == 1
    found = {(v["importer"], v["imported"], v["to_layer"]) for v in outcome.report()["violations"]}
    assert found == {
        ("rentals.services.booking", "rentals.deps", None),
        ("rentals.domain.bike", "rentals.main", None),
        ("rentals.db.bikes", "rentals.deps", None),
    }


def test_interface_code_may_import_the_provider_module(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = "from rentals.deps import Booking\nfrom rentals.services.booking import book_bike\n"
    files = {
        **CLEAN_TREE,
        "rentals/deps.py": "from rentals.db.bikes import SqlBikeStore\n",
        "rentals/routers/bikes.py": router,
    }
    write_tree(tmp_path, files)
    outcome = run_map("--json")
    assert outcome.code == 0
    assert outcome.report()["violations"] == []


def test_root_import_text_names_the_composition_root_and_type_only_is_not_failing(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    booking = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from rentals import deps\n"
    files = {
        **CLEAN_TREE,
        "rentals/deps.py": "",
        "rentals/services/booking.py": booking,
        "rentals/db/bikes.py": "from rentals.deps import get_session\n",
    }
    write_tree(tmp_path, files)
    outcome = run_map()
    assert outcome.code == 1
    assert (
        "rentals/db/bikes.py:1  rentals.db.bikes [infrastructure] imports "
        "rentals.deps [composition root]"
    ) in outcome.out
    report = run_map("--json").report()
    assert [v["importer"] for v in report["type_only"]] == ["rentals.services.booking"]
