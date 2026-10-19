"""Tests for the ArtifactSource ABC (PR 1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.catalog.source import ArtifactSource
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


@pytest.mark.parametrize("abc", [ArtifactSource])
def test_source_abc_cannot_be_instantiated(abc):
    with pytest.raises(TypeError):
        abc()


def test_artifact_source_subclass_can_be_instantiated():
    assert isinstance(_DummyArtifactSource(), ArtifactSource)


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
