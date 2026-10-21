"""The prompt-set names and directories (``catalog/prompt_sets.py``; D76, prU L0-24)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.catalog.prompt_sets import (
    DEFAULT_PROMPT_SET,
    LATER_PROMPT_SETS,
    PROMPT_SETS,
    is_prompt_set,
    prompt_set_dir,
    prompt_set_dirs,
    require_prompt_set,
)


def test_v1_is_the_default_and_the_later_sets_are_the_rest() -> None:
    assert PROMPT_SETS == ("v1", "v2")
    assert DEFAULT_PROMPT_SET == "v1"
    assert LATER_PROMPT_SETS == ("v2",)


def test_v1_lives_in_the_prompts_root_and_a_later_set_in_its_own_directory() -> None:
    root = Path("catalog/core/prompts")
    assert prompt_set_dir(root, "v1") == root
    assert prompt_set_dir(root, "v2") == root / "v2"


def test_the_v1_walk_skips_every_later_set_directory() -> None:
    root = Path("playbook/prompts")
    assert prompt_set_dirs(root) == (root / "v2",)


@pytest.mark.parametrize("bad", ["v3", "V2", "", None, 2])
def test_an_unknown_set_is_refused_by_name(bad: object) -> None:
    assert not is_prompt_set(bad)
    with pytest.raises(ValueError, match=r"unknown prompt set .*; expected one of 'v1', 'v2'"):
        require_prompt_set(bad)


def test_an_unknown_set_never_names_a_directory() -> None:
    with pytest.raises(ValueError, match="unknown prompt set 'v3'"):
        prompt_set_dir(Path("prompts"), "v3")  # type: ignore[arg-type]  # the runtime guard


@pytest.mark.parametrize("name", ["v1", "v2"])
def test_every_set_is_accepted(name: str) -> None:
    assert is_prompt_set(name)
    assert require_prompt_set(name) == name
