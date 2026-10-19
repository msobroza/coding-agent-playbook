"""Tests for the StateSource ABC (PR 1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.config.files import StateSource
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.config.tables.hooks import PolicyTables


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


@pytest.mark.parametrize("abc", [StateSource])
def test_source_abc_cannot_be_instantiated(abc):
    with pytest.raises(TypeError):
        abc()


def test_state_source_subclass_can_be_instantiated():
    assert isinstance(_DummyStateSource(), StateSource)


def test_state_source_load_primary_config_defaults_to_load_config():
    """A third-party source written before ``load_primary_config`` existed
    keeps working: the concrete default returns whatever ``load_config`` does."""
    loaded = object()

    class _OldStyleStateSource(_DummyStateSource):
        def load_config(self):
            return loaded

    assert _OldStyleStateSource().load_primary_config() is loaded


def test_state_source_load_local_overrides_defaults_to_empty():
    """A source with no per-developer file has no local overrides to ignore."""
    assert _DummyStateSource().load_local_overrides() == {}


def test_state_source_load_policy_tables_reads_the_primary_config():
    """The concrete default (prK §B.1): the committed config's extension
    tables, with the local overrides only recorded."""
    config = Config(1, ProjectMeta("x", "python-library"), "0.1")
    config.extra_tables = {"hooks": {"enabled": True}, "links": {}}

    class _OneConfigSource(_DummyStateSource):
        def load_config(self):
            return config

        def load_local_overrides(self):
            return {"guardrails": {"git": {}}}

    assert _OneConfigSource().load_policy_tables() == PolicyTables(
        hooks={"enabled": True}, local_keys=("guardrails.git",)
    )
