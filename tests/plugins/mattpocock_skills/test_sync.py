"""End-to-end init and sync with the ``mattpocock_skills`` bundled plugin enabled.

specs/prT-mattpocock-skills.md sections 7.1 and 9.2: ``playbook init
--non-interactive --overlays coding_agent_playbook.plugins.mattpocock_skills``
with adapters ``continue,claude_code,opencode,shared_skills`` lands every
present skill byte for byte in the three native skill roots and as a Continue
prompt; ``playbook validate`` and ``playbook sync --check`` then pass.
"""

from __future__ import annotations

import argparse
import os
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import split_frontmatter
from tests.fakes import FakeGitClient
from tests.plugins.mattpocock_skills._expectations import (
    FINAL_IDS,
    PLUGIN_NAME,
    SKILLS_ROOT,
    present_skill_ids,
    split_skill,
)
from tests.plugins.mattpocock_skills.conftest import init_probe
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILLS = present_skill_ids()
#: What the ``SkillWriter`` adds between the frontmatter and the source body.
_SENTINEL_BODY_PREFIX = f"<!-- {SENTINEL} -->\n\n"


def _files(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (POSIX path) with its bytes; empty when ``root`` is absent."""
    if not root.is_dir():
        return {}
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in paths}


def _source_files(root: Path) -> dict[str, bytes]:
    """Like :func:`_files`, minus bytecode caches (sync never copies them)."""
    return {rel: data for rel, data in _files(root).items() if "__pycache__" not in rel}


def test_init_writes_the_top_level_overlay_key(synced_repo: Path) -> None:
    config = tomllib.loads((synced_repo / ".coding-agent-playbook.toml").read_text("utf-8"))
    assert config["overlays_enabled"] == [PLUGIN_NAME]


@pytest.mark.parametrize("root", NATIVE_SKILL_ROOTS)
@pytest.mark.parametrize("skill_id", _SKILLS)
def test_sync_writes_the_source_frontmatter_and_the_sentinel_then_the_source_body(
    synced_repo: Path, root: str, skill_id: str
) -> None:
    written = (synced_repo / root / skill_id / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(written)
    source_frontmatter, source_body = split_skill(skill_id)
    assert frontmatter == source_frontmatter, f"{root}/{skill_id}: frontmatter changed"
    assert body == _SENTINEL_BODY_PREFIX + source_body, f"{root}/{skill_id}: body changed"


@pytest.mark.parametrize("root", NATIVE_SKILL_ROOTS)
@pytest.mark.parametrize("skill_id", _SKILLS)
def test_sync_copies_references_and_scripts_byte_for_byte(
    synced_repo: Path, root: str, skill_id: str
) -> None:
    for subdir in ("references", "scripts"):
        source = _source_files(SKILLS_ROOT / skill_id / subdir)
        # Unfiltered on the synced side: a bytecode cache leaking into a root fails here.
        assert _files(synced_repo / root / skill_id / subdir) == source, (
            f"{root}/{skill_id}/{subdir}"
        )
    scripts = synced_repo / root / skill_id / "scripts"
    if os.name != "nt":  # Windows has no executable bit to check
        for rel in _source_files(SKILLS_ROOT / skill_id / "scripts"):
            assert os.access(scripts / rel, os.X_OK), f"{root}/{skill_id}/scripts/{rel}"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_the_three_native_roots_hold_the_same_bytes(synced_repo: Path, skill_id: str) -> None:
    trees = [_files(synced_repo / root / skill_id) for root in NATIVE_SKILL_ROOTS]
    assert trees[0], f"{NATIVE_SKILL_ROOTS[0]}/{skill_id} is empty"
    assert all(tree == trees[0] for tree in trees[1:])


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_continue_prompt_ends_with_the_source_body(synced_repo: Path, skill_id: str) -> None:
    text = (synced_repo / ".continue" / "prompts" / f"{skill_id}.md").read_text(encoding="utf-8")
    assert SENTINEL in text.split("\n", 1)[0]
    assert text.endswith(split_skill(skill_id)[1])


def test_validate_and_sync_check_pass_with_the_plugin_enabled(
    synced_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _validate.run(argparse.Namespace(repo_root=str(synced_repo))) == 0, (
        capsys.readouterr().out
    )
    assert _sync.execute(synced_repo, check=True, git=FakeGitClient()) == 0, capsys.readouterr().out


def test_lockfile_stamps_every_plugin_skill_entry_with_kind_and_source(synced_repo: Path) -> None:
    lockfile = tomllib.loads((synced_repo / ".coding-agent-playbook.lock").read_text("utf-8"))
    entries = [e for e in lockfile["entries"] if e.get("artifact_id") in set(_SKILLS)]
    assert {e["artifact_id"] for e in entries} == set(_SKILLS)
    for entry in entries:
        assert entry["kind"] == "skill", entry
        assert entry["source"] == PLUGIN_NAME, entry


@pytest.mark.usefixtures("hermetic_git_env")
def test_init_without_the_overlay_writes_none_of_the_ids(tmp_path: Path) -> None:
    repo = init_probe(tmp_path, overlays=None)
    for root in NATIVE_SKILL_ROOTS:
        assert sorted(FINAL_IDS & {p.name for p in _dir_entries(repo / root)}) == [], root
    prompts = {p.stem for p in _dir_entries(repo / ".continue" / "prompts")}
    assert sorted(FINAL_IDS & prompts) == []


def _dir_entries(root: Path) -> list[Path]:
    return list(root.iterdir()) if root.is_dir() else []
