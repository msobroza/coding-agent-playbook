"""Smoke tests for entry-point discovery and package metadata (PR 1)."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
_HOOK_HANDLERS_GROUP = "coding_agent_playbook.hook_handlers"

_GROUPS = [
    "coding_agent_playbook.adapters",
    "coding_agent_playbook.overlays",
    "coding_agent_playbook.artifact_sources",
    "coding_agent_playbook.state_sources",
    "coding_agent_playbook.runners",
    "coding_agent_playbook.judges",
    _HOOK_HANDLERS_GROUP,
]


def _project_table() -> dict[str, Any]:
    with _PYPROJECT.open("rb") as handle:
        project: dict[str, Any] = tomllib.load(handle)["project"]
    return project


@pytest.mark.parametrize("group", _GROUPS)
def test_entry_point_group_loads(group):
    # Empty in PR 1; later PRs populate. The contract is that discovery works.
    assert isinstance(list(metadata.entry_points(group=group)), list)


def test_engine_metadata_resolves():
    assert metadata.metadata("coding-agent-playbook")["Name"] == "coding-agent-playbook"


def test_hook_handlers_group_declared_in_pyproject() -> None:
    # Declared empty in Track Pb (P-D5); out-of-tree hook handler packages
    # register here, and the engine's own handlers are builtins (§D.1).
    assert _project_table()["entry-points"][_HOOK_HANDLERS_GROUP] == {}


def test_no_playbook_hook_script_before_k2() -> None:
    # The console script lands with its module in K2, so no installed script
    # ever points at a module that does not exist yet (§D.11, P-D5).
    assert "playbook-hook" not in _project_table()["scripts"]
