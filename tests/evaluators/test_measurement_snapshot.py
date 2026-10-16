"""Measurement snapshots: ``--emit-measurements`` writes them, ``--baseline json:`` reads them (prK §F.0.3 item 4)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.measurement_snapshot import (
    SNAPSHOT_SCHEMA,
    SnapshotError,
    read_snapshot,
    write_snapshot,
)
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from pathlib import Path

_MEASUREMENTS = [
    Measurement("cyclomatic_complexity", "src/a.py::f", 3.0),
    Measurement("coverage", "src/a.py", 87.5),
]


def test_write_then_read_round_trips_measurements_and_tree(tmp_path: Path) -> None:
    path = tmp_path / "cov.json"

    write_snapshot(path, _MEASUREMENTS, tree="4b825dc6")

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document == {
        "schema": SNAPSHOT_SCHEMA,
        "tree": "4b825dc6",
        "measurements": [
            {"evaluator": "cyclomatic_complexity", "scope_key": "src/a.py::f", "value": 3.0},
            {"evaluator": "coverage", "scope_key": "src/a.py", "value": 87.5},
        ],
    }
    assert read_snapshot(path) == _MEASUREMENTS


def test_tree_is_null_when_unknown(tmp_path: Path) -> None:
    path = tmp_path / "snap.json"

    write_snapshot(path, [], tree=None)

    assert json.loads(path.read_text(encoding="utf-8"))["tree"] is None
    assert read_snapshot(path) == []


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        ("{not json", "not JSON"),
        ("[]", "expected a JSON object"),
        ('{"schema": 2, "tree": null, "measurements": []}', "schema 2 is not supported"),
        ('{"schema": 1, "tree": 3, "measurements": []}', "'tree' must be a string or null"),
        ('{"schema": 1, "tree": null}', "'measurements' must be a list"),
        (
            '{"schema": 1, "tree": null, "measurements": [{"evaluator": "x", "value": 1}]}',
            "measurement 0 must be",
        ),
        (
            '{"schema": 1, "tree": null, "measurements": '
            '[{"evaluator": "x", "scope_key": "a", "value": true}]}',
            "measurement 0 must be",
        ),
        (
            '{"schema": 1, "tree": null, "measurements": '
            '[{"evaluator": "x", "scope_key": "a", "value": NaN}]}',
            "measurement 0 must be",
        ),
    ],
    ids=["not-json", "not-object", "schema", "tree", "no-list", "no-scope", "bool", "nan"],
)
def test_bad_snapshot_raises_naming_path_and_problem(
    tmp_path: Path, content: str, problem: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(SnapshotError) as excinfo:
        read_snapshot(path)

    assert str(excinfo.value).startswith(f"bad measurement snapshot {path}: ")
    assert problem in str(excinfo.value)


def test_unreadable_snapshot_raises(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="cannot read measurement snapshot"):
        read_snapshot(tmp_path / "missing.json")
