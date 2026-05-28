"""Tests for the Adapter ABC (PR 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.adapters.base import Adapter


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


def test_write_skill_degrades_to_prompt():
    class _Skill:
        def to_prompt(self):
            return "from-skill"

    adapter = _DummyAdapter()
    result = adapter.write_skill(_Skill(), Path("."))
    assert adapter.written_prompts == ["from-skill"]
    assert result == [Path("from-skill.md")]


def test_cleanup_stale_not_implemented_until_pr6():
    with pytest.raises(NotImplementedError):
        _DummyAdapter().cleanup_stale(set(), Path("."))
