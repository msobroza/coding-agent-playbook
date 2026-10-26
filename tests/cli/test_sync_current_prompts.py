"""``playbook sync`` renders the current text of the core prompts (ADR 0012, #300).

The former v2 prompt set replaced the v1 text in place, so a sync writes the text
that points to skills under the prompt names and slash commands v1 had, and a
config that still picks a prompt set with ``prompts`` stops before anything is
written.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.config.schema import PROMPTS_KEY_REMOVED
from coding_agent_playbook.detector.config_filenames import CONFIG_FILENAME
from tests.conftest import _DEFAULT_CONFIG

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

pytestmark = pytest.mark.catalog

#: Every core prompt's slash command, as v1 named them: the current text keeps them.
_SLASHES: Final = {
    "characterize": "characterize",
    "explain": "explain",
    "find-injected-vulnerability": "find-injected-vulnerability",
    "generate-tests": "generate-tests",
    "make-testable": "make-testable",
    "refactor": "refactor",
    "review": "review-core",
    "review-architecture": "review-architecture",
    "security-review": "security-review-core",
}

#: A probe repo every core prompt applies to (pytest, FastAPI, an ML stack).
_ALL_FACTS_DEPS: Final = ["pytest", "fastapi", "sqlalchemy", "torch", "pandas", "numpy"]

#: A heading only the former v2 text has: the core skills a task loads first.
_SKILLS_HEADING: Final = "## Skills for this task"


def test_a_sync_writes_the_former_v2_text_under_the_v1_slash_commands(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = make_synthetic_repo(tmp_path, pyproject_extras={"dependencies": _ALL_FACTS_DEPS})

    assert sync_cmd.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0

    for prompt_id, slash in _SLASHES.items():
        for command_dir in (".claude/commands", ".opencode/command"):
            command = repo / command_dir / f"{slash}.md"
            assert command.is_file(), f"{prompt_id} has no {command_dir}/{slash}.md"
            assert _SKILLS_HEADING in command.read_text(encoding="utf-8"), command


@pytest.mark.parametrize("value", ["v1", "v2"])
def test_a_sync_with_a_prompts_key_fails_with_the_removal_message_and_writes_nothing(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    config = f'prompts = "{value}"\n' + _DEFAULT_CONFIG
    repo = make_synthetic_repo(tmp_path, config_text=config)

    assert main(["sync", "--repo-root", str(repo)]) == 2

    assert capsys.readouterr().err == f"error: {CONFIG_FILENAME}: {PROMPTS_KEY_REMOVED}\n"
    assert not (repo / ".claude").exists()
