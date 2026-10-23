"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill: JSON output, usage errors and the real CLI.

Shared trees and run helpers live in ``_scripts.py``; the ``layer_map`` and ``run_map``
fixtures in ``conftest.py`` (prU D2, D25).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tests.core_skills.python_architecture._scripts import (
    CLEAN_TREE,
    CYCLE_TREE,
    ORM_VIOLATION,
    ROUTER_IMPORTS_ORM,
    Outcome,
    elif_chain_module,
    plus_chain_module,
    run_script,
    write_tree,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.catalog


# --- output and usage ---------------------------------------------------------------


def test_json_output_schema(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    admin = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import rentals.db.bikes\n"
    write_tree(tmp_path, {**ROUTER_IMPORTS_ORM, **CYCLE_TREE, "rentals/routers/admin.py": admin})
    report = run_map("--json").report()
    assert {"layers", "flows", "violations", "cycles", "type_only"} <= set(report)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in report["layers"].items())
    assert report["flows"]
    assert all([type(item) for item in flow] == [str, str, int] for flow in report["flows"])
    records = report["violations"] + report["type_only"]
    assert report["violations"]
    assert report["type_only"]
    for record in records:
        assert set(record) == {"importer", "imported", "from_layer", "to_layer", "file", "line"}
        assert isinstance(record["line"], int)
    assert report["cycles"]
    assert all(isinstance(m, str) for group in report["cycles"] for m in group)


@pytest.mark.parametrize(
    "args",
    [
        ["no-such-dir"],
        ["interface=api"],
        [".", "--layer", "interface"],
        [".", "--layer", "=api"],
        [".", "--allow", "interface=warehouse"],
        [".", "--allow", "warehouse=domain"],
        [".", "--root-module", "/"],
        [".", "--root-module", "nowhere"],
        [".", "--no-such-flag"],
    ],
)
def test_usage_errors_exit_2(
    tmp_path: Path, run_map: Callable[..., Outcome], args: list[str]
) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map(*args)
    assert outcome.code == 2
    assert outcome.out == ""
    assert "usage: layer_map.py" in outcome.err


def test_unparseable_file_is_reported_on_stderr_and_skipped(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/services/broken.py": "def oops(:\n"})
    outcome = run_map("--json")
    assert outcome.code == 0
    assert "rentals/services/broken.py" in outcome.err
    assert outcome.report()["violations"] == []


# --- the real command line ----------------------------------------------------------


def test_cli_exit_statuses(tmp_path: Path) -> None:
    clean, dirty = tmp_path / "clean", tmp_path / "dirty"
    write_tree(clean, CLEAN_TREE)
    write_tree(dirty, ROUTER_IMPORTS_ORM)
    assert run_script(clean).returncode == 0
    result = run_script(dirty, ".", "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["violations"] == [ORM_VIOLATION]
    usage = run_script(clean, ".", "--allow", "nowhere=domain")
    assert usage.returncode == 2
    assert "nowhere" in usage.stderr


def test_cli_reports_unparseable_files_on_stderr(tmp_path: Path) -> None:
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/db/legacy.py": "print 'old'\n"})
    result = run_script(tmp_path, ".", "--json")
    assert result.returncode == 0
    assert "skipped rentals/db/legacy.py" in result.stderr
    json.loads(result.stdout)


def test_cli_survives_a_long_elif_chain_and_a_deep_expression(tmp_path: Path) -> None:
    # Regression: the recursive import visitor overflowed the stack on ~330 elif
    # branches or a ~900-term `+` chain (both valid Python), killing the whole scan
    # with a traceback, empty stdout and exit 1. A fresh interpreter, as an agent runs it.
    files = {
        **CLEAN_TREE,
        "rentals/routers/dispatch.py": elif_chain_module(
            1000, "from rentals.db.bikes import BikeRow"
        ),
        "rentals/routers/labels.py": plus_chain_module(900, "import rentals.db.bikes"),
    }
    write_tree(tmp_path, files)
    result = run_script(tmp_path, ".", "--json")
    assert result.returncode == 1, result.stderr
    assert "RecursionError" not in result.stderr
    found = {(v["importer"], v["line"]) for v in json.loads(result.stdout)["violations"]}
    assert found == {("rentals.routers.dispatch", 2003), ("rentals.routers.labels", 2)}
