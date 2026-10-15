"""Tests for the ArtifactSource and StateSource ABCs (PR 1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Hook, HookSchemaError
from tests.hook_samples import hook_frontmatter


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


def test_state_source_load_primary_config_defaults_to_load_config():
    """A third-party source written before ``load_primary_config`` existed
    keeps working: the concrete default returns whatever ``load_config`` does."""
    loaded = object()

    class _OldStyleStateSource(_DummyStateSource):
        def load_config(self):
            return loaded

    assert _OldStyleStateSource().load_primary_config() is loaded


def test_list_hooks_default_is_empty():
    """``list_hooks`` is concrete (prK §A.5): a source written before hooks
    existed, like ``_DummyArtifactSource``, still instantiates and lists none."""
    assert _DummyArtifactSource().list_hooks() == []


def test_collect_hooks_default_wraps_list_hooks():
    hook = Hook(hook_frontmatter(), "", "", False, None, "third_party")

    class _OneHookSource(_DummyArtifactSource):
        def list_hooks(self):
            return [hook]

    assert _OneHookSource().collect_hooks() == ([hook], [])


def test_collect_hooks_default_records_a_raised_hook_schema_error():
    """``tolerate_hook_errors`` (prK §P P8c) must not crash on a third-party
    source whose ``list_hooks`` fails loudly; its error is recorded instead."""
    error = HookSchemaError("remote:guard-x", "timeout", "2s", "a number of seconds")

    class _FailingSource(_DummyArtifactSource):
        def list_hooks(self):
            raise error

    assert _FailingSource().collect_hooks() == ([], [error])
