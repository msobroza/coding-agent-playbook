"""``playbook validate`` refuses a prompt set with a missing or renamed twin (D76; prU L0-24).

Each layer's ``prompts/v2/`` holds the v2 twin of its v1 prompts, matched by id.
A v2 prompt without a v1 twin, and a v1 prompt without a v2 twin once the layer
has a v2 set, are errors; a twin must keep the name, slash command and
``includes_rules`` of its v1 prompt, so the listing never changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.validation.prompts import check_prompt_set_twins

if TYPE_CHECKING:
    from pathlib import Path


def _write_prompt(
    path: Path, prompt_id: str, *, slash: str | None = None, includes_rules: str = "[]"
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {prompt_id}\nname: {prompt_id}\ndescription: d\n"
        f"slash: {slash or prompt_id}\nincludes_rules: {includes_rules}\n---\nBody.\n",
        encoding="utf-8",
    )


def _messages(repo: Path) -> list[tuple[str, str]]:
    source = FileSystemArtifactSource(repo_root=repo)
    return [
        (error.path, error.message)
        for error in check_prompt_set_twins(source)
        if "playbook/prompts" in error.path
    ]


def test_a_layer_without_a_v2_set_and_a_complete_v2_set_both_pass(tmp_path: Path) -> None:
    prompts = tmp_path / "playbook" / "prompts"
    _write_prompt(prompts / "tidy-up.md", "tidy-up")
    assert _messages(tmp_path) == []
    _write_prompt(prompts / "v2" / "tidy-up.md", "tidy-up")
    assert _messages(tmp_path) == []


def test_the_engine_catalog_passes() -> None:
    from pathlib import Path

    assert check_prompt_set_twins(FileSystemArtifactSource(repo_root=Path("/no/such/repo"))) == []


def test_a_v2_prompt_without_a_v1_twin_is_an_error(tmp_path: Path) -> None:
    prompts = tmp_path / "playbook" / "prompts"
    _write_prompt(prompts / "tidy-up.md", "tidy-up")
    _write_prompt(prompts / "v2" / "tidy-up.md", "tidy-up")
    _write_prompt(prompts / "v2" / "orphan.md", "orphan")

    [(path, message)] = _messages(tmp_path)
    assert path == str(prompts / "v2" / "orphan.md")
    assert message.startswith("v2 prompt 'orphan' has no v1 twin")


def test_a_v1_prompt_without_a_v2_twin_is_an_error_once_the_layer_has_a_v2_set(
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "playbook" / "prompts"
    _write_prompt(prompts / "tidy-up.md", "tidy-up")
    _write_prompt(prompts / "explain-it.md", "explain-it")
    _write_prompt(prompts / "v2" / "tidy-up.md", "tidy-up")

    [(path, message)] = _messages(tmp_path)
    assert path == str(prompts / "explain-it.md")
    assert message.startswith("prompt 'explain-it' has no v2 twin")
    assert str(prompts / "v2") in message


def test_a_twin_that_renames_its_command_or_changes_its_rules_is_an_error(
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "playbook" / "prompts"
    _write_prompt(prompts / "tidy-up.md", "tidy-up", includes_rules="[pytest]")
    _write_prompt(prompts / "v2" / "tidy-up.md", "tidy-up", slash="tidy", includes_rules="[]")

    messages = [message for _path, message in _messages(tmp_path)]
    assert messages == [
        "v2 prompt 'tidy-up' changes slash from 'tidy-up' to 'tidy'; "
        "a twin keeps its v1 prompt's slash",
        "v2 prompt 'tidy-up' changes includes_rules from ['pytest'] to []; "
        "a twin keeps its v1 prompt's includes_rules",
    ]
