"""Smoke tests for entry-point discovery and package metadata (PR 1)."""

from __future__ import annotations

from importlib import metadata

import pytest

_GROUPS = [
    "coding_agent_playbook.adapters",
    "coding_agent_playbook.overlays",
    "coding_agent_playbook.artifact_sources",
    "coding_agent_playbook.state_sources",
    "coding_agent_playbook.runners",
    "coding_agent_playbook.judges",
]


@pytest.mark.parametrize("group", _GROUPS)
def test_entry_point_group_loads(group):
    # Empty in PR 1; later PRs populate. The contract is that discovery works.
    assert isinstance(list(metadata.entry_points(group=group)), list)


def test_engine_metadata_resolves():
    assert metadata.metadata("coding-agent-playbook")["Name"] == "coding-agent-playbook"
