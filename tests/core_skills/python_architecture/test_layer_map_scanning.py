"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill: scanned files and import resolution.

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


# --- import resolution --------------------------------------------------------------


def test_relative_imports_resolve_to_scanned_modules(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        from ..services import booking
        from ..db.bikes import BikeRow
        from .. import domain
        from .... import beyond_the_top
        """
    package_init = "from .bikes import router\n"
    write_tree(
        tmp_path,
        {
            **CLEAN_TREE,
            "rentals/routers/bikes.py": router,
            "rentals/routers/__init__.py": package_init,
        },
    )
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["violations"] == [{**ORM_VIOLATION, "line": 2}]
    assert ["interface", "application", 1] in report["flows"]
    assert ["interface", "domain", 1] in report["flows"]


def test_src_layout_scans_src_only(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    write_tree(tmp_path / "src", ROUTER_IMPORTS_ORM)
    outside = {"tools/routers/seed.py": "from db import fixtures\n", "db/fixtures.py": ""}
    write_tree(tmp_path, outside)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["scanned"] == "src"
    assert report["violations"] == [{**ORM_VIOLATION, "file": "src/rentals/routers/bikes.py"}]
    assert all(module.startswith("rentals") for module in report["layers"])


def test_src_without_python_files_falls_back_to_root(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: a maturin src/lib.rs (or a JS src/) used to be scanned instead of
    # the Python package beside it, giving 0 modules and a clean exit 0.
    write_tree(tmp_path, {**ROUTER_IMPORTS_ORM, "src/lib.rs": "fn main() {}\n"})
    write_tree(tmp_path, {"src/tests/test_lib.py": "import rentals\n"})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["scanned"] == "."
    assert report["violations"] == [ORM_VIOLATION]


@pytest.mark.parametrize(
    "files",
    [{}, {"src/lib.rs": "fn main() {}\n"}, {"tests/test_bikes.py": "import rentals\n"}],
    ids=["empty", "rust-src-only", "tests-only"],
)
def test_nothing_to_scan_is_a_usage_error(
    tmp_path: Path, run_map: Callable[..., Outcome], files: dict[str, str]
) -> None:
    write_tree(tmp_path, files)
    outcome = run_map("--json")
    assert outcome.code == 2
    assert outcome.out == ""
    assert "found no Python module to scan" in outcome.err


def test_root_inside_a_package_keeps_the_package_prefix(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map("rentals", "--json")
    assert outcome.code == 1
    assert outcome.report()["violations"][0]["importer"] == "rentals.routers.bikes"


def test_third_party_and_unknown_imports_are_ignored(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        import os
        import sqlalchemy.orm
        from fastapi import APIRouter
        import models
        from db import Session
        from rentals.payments.gateway import charge
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": router})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert [flow for flow in report["flows"] if flow[0] == "interface"] == []


def test_test_code_and_hidden_or_vendored_dirs_are_not_scanned(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    reach_in = "from rentals.db.bikes import SqlBikeStore\n"
    extra = {
        "tests/routers/test_bikes.py": reach_in,
        "rentals/routers/conftest.py": reach_in,
        "rentals/routers/test_payloads.py": reach_in,
        "rentals/routers/payloads_test.py": reach_in,
        ".venv/lib/routers/client.py": "from db import pool\n",
        "node_modules/views/page.py": "from db import pool\n",
    }
    write_tree(tmp_path, {**CLEAN_TREE, **extra})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    scanned = set(report["layers"]) | set(report["unlayered"])
    assert all(module.startswith("rentals") for module in scanned)
    assert not any("test" in module for module in scanned)
