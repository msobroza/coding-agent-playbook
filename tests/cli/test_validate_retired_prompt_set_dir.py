"""``playbook validate`` refuses a leftover ``prompts/v2/`` in any layer (ADR 0012, #300).

Prompt sets were removed, so every file under a layer's ``prompts/`` is read as a
prompt: a ``v2/`` twin left in a repo-local layer would load beside the prompt of
the same id, and its file name would decide which text renders. Validate names
the directory and the move to make; the validate-gated sync writes nothing.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.validation.prompts import check_retired_prompt_set_dirs
from tests.conftest import _write_prompt

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    SyntheticRepoFactory = Callable[..., Path]


def _repo_with_a_v2_twin(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory) -> Path:
    repo = make_synthetic_repo(tmp_path, prompts=[("tidy-up", {"body": "Current text\n"})])
    _write_prompt(repo / "playbook" / "prompts" / "v2" / "tidy-up.md", "tidy-up", body="Old v2\n")
    return repo


def test_validate_names_the_retired_directory_and_the_move(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_a_v2_twin(tmp_path, make_synthetic_repo)

    assert main(["validate", "--repo-root", str(repo)]) == 1

    captured = capsys.readouterr()
    retired = repo / "playbook" / "prompts" / "v2"
    assert f"FAIL {retired}: {retired}/ held a prompt set" in captured.out + captured.err
    assert "prompt sets were removed (ADR 0012)" in captured.out + captured.err


def test_sync_writes_nothing_while_a_v2_twin_is_left(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _repo_with_a_v2_twin(tmp_path, make_synthetic_repo)

    assert sync_cmd.run(argparse.Namespace(repo_root=str(repo), check=False)) == 1

    assert not (repo / ".claude" / "commands" / "tidy-up.md").exists()


def test_layers_without_a_v2_directory_pass(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = make_synthetic_repo(tmp_path, prompts=[("tidy-up", {})])
    (repo / "playbook" / "prompts" / "notes").mkdir()

    assert check_retired_prompt_set_dirs(FileSystemArtifactSource(repo_root=repo)) == []
