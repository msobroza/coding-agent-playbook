"""Tests for the Adapter ABC (PR 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.types import Skill


class _DummyAdapter(Adapter):
    name = "dummy"

    def __init__(self) -> None:
        self.written_prompts: list[object] = []

    def write_rule(self, rule, repo_root):
        return []

    def write_prompt(self, prompt, repo_root):
        self.written_prompts.append(prompt)
        return [repo_root / f"{prompt}.md"]


def test_adapter_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Adapter()  # type: ignore[abstract]


def test_concrete_subclass_can_be_instantiated():
    assert isinstance(_DummyAdapter(), Adapter)


def test_finalize_defaults_to_no_output():
    assert _DummyAdapter().finalize(Path(".")) == []


def test_write_skill_default_degradation_deferred_to_pr6():
    # The default write_skill degrades a skill via Skill.to_prompt(), which is
    # not implemented until the Continue adapter (PR 6).
    skill = Skill(
        frontmatter={"name": "demo"},
        body="",
        scripts_dir=None,
        references_dir=None,
        source_package="pkg",
    )
    with pytest.raises(NotImplementedError):
        _DummyAdapter().write_skill(skill, Path("."))


def test_cleanup_stale_not_implemented_until_pr6():
    with pytest.raises(NotImplementedError):
        _DummyAdapter().cleanup_stale(set(), Path("."))
