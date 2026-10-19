"""Structure + opt-in tests for the bundled ``superpowers`` plugin (SPEC §11.5).

The plugin is a directory under ``catalog/plugins/``, layered like an overlay
package but never imported. These tests pin its layout and listing, that it is
**off by default**, the per-skill shape the engine's skill sync relies on
(including the full ``references/`` inventory), and the MIT attribution files
that must ship with every copy.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.catalog.roots import bundled_plugins
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from tests.plugins.superpowers_expectations import (
    EXPECTED_LICENSE_COPIES,
    EXPECTED_REFERENCE_FILES,
    EXPECTED_SKILL_IDS,
    PLUGIN_NAME,
    PLUGIN_ROOT,
    SKILLS_ROOT,
    SYNCED_SKILL_ENTRIES,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.skill import Skill

pytestmark = pytest.mark.catalog

# Agent Skills naming rule: lowercase alphanumerics separated by single hyphens.
_SKILL_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_ID_LENGTH = 64
_MAX_DESCRIPTION_LENGTH = 1024


def _pack_skills(skills: list[Skill]) -> list[Skill]:
    return [skill for skill in skills if skill.source_package == PLUGIN_NAME]


def test_superpowers_plugin_layout() -> None:
    """Pure content: ``skills/`` plus the plugin-root files, listed by directory name."""
    entries = list(PLUGIN_ROOT.iterdir())
    assert sorted(path.name for path in entries if path.is_dir()) == ["skills"]
    assert {"LICENSE", "ATTRIBUTIONS.md", "README.md"} <= {p.name for p in entries if p.is_file()}
    assert PLUGIN_NAME in bundled_plugins()


def test_pack_is_off_by_default(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=tmp_path)
    skills = source.list_skills()
    assert _pack_skills(skills) == []
    assert {str(s.frontmatter.get("id")) for s in skills}.isdisjoint(EXPECTED_SKILL_IDS)


def test_overlay_yields_exactly_the_expected_skills(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PLUGIN_NAME])
    pack_ids = [skill.frontmatter.get("id") for skill in _pack_skills(source.list_skills())]
    assert len(pack_ids) == len(EXPECTED_SKILL_IDS)
    assert set(pack_ids) == EXPECTED_SKILL_IDS


def test_overlay_adds_no_rules_or_prompts(tmp_path: Path) -> None:
    plain = FileSystemArtifactSource(repo_root=tmp_path)
    with_pack = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PLUGIN_NAME])
    assert len(with_pack.list_rules()) == len(plain.list_rules())
    assert len(with_pack.list_prompts()) == len(plain.list_prompts())


def test_skills_root_holds_exactly_the_expected_skill_dirs() -> None:
    assert {path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()} == EXPECTED_SKILL_IDS


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_skill_dir_holds_only_synced_entries(skill_id: str) -> None:
    entries = {path.name for path in (SKILLS_ROOT / skill_id).iterdir()}
    assert "SKILL.md" in entries
    dropped = entries - SYNCED_SKILL_ENTRIES
    assert not dropped, f"{skill_id}: sync would silently drop {sorted(dropped)}"


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_skill_frontmatter_identity(skill_id: str) -> None:
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, _ = split_frontmatter(text)
    # ``id`` first: the engine keys skills by it, and the port inserts it ahead
    # of the upstream ``name``/``description`` so the diff stays one line.
    assert next(iter(frontmatter)) == "id", f"keys: {list(frontmatter)}"
    assert frontmatter["id"] == frontmatter["name"] == skill_id
    assert _SKILL_ID_RE.match(skill_id)
    assert len(skill_id) <= _MAX_ID_LENGTH


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_skill_description_is_bounded_string(skill_id: str) -> None:
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    description = split_frontmatter(text)[0].get("description")
    assert isinstance(description, str)
    assert 1 <= len(description) <= _MAX_DESCRIPTION_LENGTH


def test_pack_ships_exactly_the_expected_reference_files() -> None:
    shipped = {
        path.relative_to(SKILLS_ROOT).as_posix()
        for path in SKILLS_ROOT.glob("*/references/**/*")
        if path.is_file()
    }
    assert shipped == EXPECTED_REFERENCE_FILES


@pytest.mark.parametrize("license_copy", sorted(EXPECTED_LICENSE_COPIES))
def test_every_skill_carries_the_mit_notice(license_copy: str) -> None:
    # MIT: the notice must be in every copy; sync copies each skill directory
    # (with references/) into consumer repos, so each skill carries its own.
    copy = (SKILLS_ROOT / license_copy).read_bytes()
    assert copy == (PLUGIN_ROOT / "LICENSE").read_bytes(), f"{license_copy} drifted from LICENSE"


def test_diagnosing_pack_attribution_note_lists_every_skill() -> None:
    # The skill-timeline analyst attributes invocations to superpowers by this
    # list when the skills come from the rendered (un-namespaced) pack.
    prompt = SKILLS_ROOT / "diagnosing-superpowers/references/prompts/skill-timeline.md"
    note = prompt.read_text(encoding="utf-8").split("rendered skills pack", 1)[1]
    note = " ".join(note.split("\n\n", 1)[0].split())
    missing = sorted(sid for sid in EXPECTED_SKILL_IDS if sid not in note)
    assert not missing, f"skill-timeline.md pack note lacks {missing}"


def test_license_keeps_mit_copyright_and_permission_notice() -> None:
    text = " ".join((PLUGIN_ROOT / "LICENSE").read_text(encoding="utf-8").split())
    assert "MIT License" in text
    assert "Copyright (c) 2025 Jesse Vincent" in text
    assert "Permission is hereby granted, free of charge" in text
    assert (
        "The above copyright notice and this permission notice shall be included in all "
        "copies or substantial portions of the Software."
    ) in text


def test_attributions_are_plain_text_and_list_every_skill() -> None:
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    assert "http://" not in text.lower()
    assert "https://" not in text.lower()
    assert "bb92a77741419a4ab5f06e711a283343f1ada0c3" in text
    assert "MIT" in text
    missing = sorted(sid for sid in EXPECTED_SKILL_IDS if f"| {sid} |" not in text)
    assert not missing, f"ATTRIBUTIONS.md skill table lacks {missing}"
