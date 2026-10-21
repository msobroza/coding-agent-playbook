"""``FileSystemArtifactSource.list_prompts`` returns one prompt set (D76; prU L0-24)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.source import FileSystemArtifactSource

if TYPE_CHECKING:
    from pathlib import Path


def _write_prompt(path: Path, prompt_id: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {prompt_id}\nname: {prompt_id}\ndescription: d\nslash: {prompt_id}\n---\n{body}",
        encoding="utf-8",
    )


def _repo_local(tmp_path: Path) -> Path:
    prompts = tmp_path / "playbook" / "prompts"
    _write_prompt(prompts / "tidy-up.md", "tidy-up", "v1 tidy\n")
    _write_prompt(prompts / "explain-it.md", "explain-it", "v1 explain\n")
    _write_prompt(prompts / "v2" / "tidy-up.md", "tidy-up", "v2 tidy\n")
    _write_prompt(prompts / "v2" / "orphan.md", "orphan", "v2 orphan\n")
    return tmp_path


def _repo_local_prompts(source: FileSystemArtifactSource) -> dict[str, str]:
    return {
        p.frontmatter.id: p.body
        for p in source.list_prompts()
        if p.source_package == "<repo-local>"
    }


def test_the_default_set_is_v1_and_never_lists_a_v2_prompt(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=_repo_local(tmp_path))
    assert _repo_local_prompts(source) == {"explain-it": "v1 explain\n", "tidy-up": "v1 tidy\n"}


def test_v2_replaces_twins_keeps_the_rest_and_never_adds_a_prompt(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=_repo_local(tmp_path), prompt_set="v2")
    assert _repo_local_prompts(source) == {"explain-it": "v1 explain\n", "tidy-up": "v2 tidy\n"}


def test_v2_keeps_the_engine_prompt_ids_and_their_order(tmp_path: Path) -> None:
    v1 = FileSystemArtifactSource(repo_root=tmp_path).list_prompts()
    v2 = FileSystemArtifactSource(repo_root=tmp_path, prompt_set="v2").list_prompts()
    assert [p.frontmatter.id for p in v2] == [p.frontmatter.id for p in v1]
