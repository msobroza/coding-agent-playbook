"""Tests for the ArtifactSource and StateSource ABCs (PR 1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.sources.base import ArtifactSource, StateSource


class _DummyArtifactSource(ArtifactSource):
    name = "dummy"

    def list_rules(self):
        return []

    def list_prompts(self):
        return []

    def list_skills(self):
        return []

    def list_eval_tasks(self):
        return []


class _DummyStateSource(StateSource):
    name = "dummy"

    def load_config(self):
        return {}

    def save_config(self, config):
        return None

    def load_lockfile(self):
        return None

    def save_lockfile(self, lockfile):
        return None


@pytest.mark.parametrize("abc", [ArtifactSource, StateSource])
def test_source_abc_cannot_be_instantiated(abc):
    with pytest.raises(TypeError):
        abc()


def test_artifact_source_subclass_can_be_instantiated():
    assert isinstance(_DummyArtifactSource(), ArtifactSource)


def test_state_source_subclass_can_be_instantiated():
    assert isinstance(_DummyStateSource(), StateSource)
