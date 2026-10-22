"""``FileSystemArtifactSource.list_prompts`` returns one prompt set (D76; prU L0-24)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.catalog.skill_rules import iter_md_files
from coding_agent_playbook.catalog.source import FileSystemArtifactSource

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.catalog.prompt_sets import PromptSet


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


def test_without_a_v2_set_the_listing_is_the_walk_list_prompts_did_before_prompt_sets(
    tmp_path: Path,
) -> None:
    """ "Byte-identical to today": before D76, ``list_prompts`` built one prompt per
    ``*.md``/``*.md.j2`` file under each layer's ``prompts/``, layer by layer; the
    render path after it is unchanged. Pinned on every real catalog layer plus a
    repo-local one, none of which has a ``prompts/v2/`` yet."""
    prompts = tmp_path / "playbook" / "prompts"
    _write_prompt(prompts / "tidy-up.md", "tidy-up", "v1 tidy\n")
    _write_prompt(prompts / "nested" / "explain-it.md", "explain-it", "v1 explain\n")
    source = FileSystemArtifactSource(repo_root=tmp_path)

    before_prompt_sets = [
        Prompt.from_markdown(md, label)
        for label, root in source.layer_roots("prompts")
        for md in iter_md_files(root)
    ]

    assert [(p.source_path, p.body) for p in source.list_prompts()] == [
        (p.source_path, p.body) for p in before_prompt_sets
    ]
    assert {"tidy-up", "explain-it"} <= {p.frontmatter.id for p in source.list_prompts()}


def test_an_unknown_prompt_set_is_refused_rather_than_listing_v1(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown prompt set 'v3'"):
        FileSystemArtifactSource(repo_root=tmp_path, prompt_set="v3")  # type: ignore[arg-type]  # the runtime guard


def test_prompt_set_layers_name_what_each_set_leaves_unrendered(tmp_path: Path) -> None:
    _repo_local(tmp_path)

    def _unrendered(prompt_set: PromptSet) -> dict[str, str]:
        source = FileSystemArtifactSource(repo_root=tmp_path, prompt_set=prompt_set)
        [layer] = source.prompt_set_layers()
        assert layer.set_dir == tmp_path / "playbook" / "prompts" / "v2"
        return {p.frontmatter.id: p.body for p in layer.unrendered}

    assert _unrendered("v1") == {"tidy-up": "v2 tidy\n", "orphan": "v2 orphan\n"}
    assert _unrendered("v2") == {"tidy-up": "v1 tidy\n"}
