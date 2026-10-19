"""Leftover-policy bounds: deletion allowlist and prune boundary (SPEC §4.2 step 9).

``OutputLocations`` is built from every installed adapter's current and retired
output locations. The link-target regression is specs/prS-skills-context.md
section 5.4.3: with two declared skill roots, one a symlink to the other, the
link target used to be pruned in 2 of the 4 combinations of declaration order
and link direction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coding_agent_playbook.sync._leftovers import OutputLocations

_CLAUDE_SKILLS = ".claude/skills"
_AGENTS_SKILLS = ".agents/skills"

needs_posix_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def _link_root(repo: Path, link: str, target: str) -> tuple[Path, Path]:
    """Make ``target`` a real directory and ``link`` a relative symlink to it."""
    target_dir = repo / target
    target_dir.mkdir(parents=True)
    link_path = repo / link
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(Path("..") / target, target_is_directory=True)
    return link_path, target_dir


def _write_skill_md(skill_dir: Path) -> Path:
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: demo\n---\n", encoding="utf-8")
    return skill_md


@needs_posix_symlinks
@pytest.mark.parametrize(
    "declared_order",
    [(_CLAUDE_SKILLS, _AGENTS_SKILLS), (_AGENTS_SKILLS, _CLAUDE_SKILLS)],
    ids=["claude-first", "agents-first"],
)
@pytest.mark.parametrize(
    ("link", "target"),
    [(_CLAUDE_SKILLS, _AGENTS_SKILLS), (_AGENTS_SKILLS, _CLAUDE_SKILLS)],
    ids=["claude-links-to-agents", "agents-links-to-claude"],
)
def test_link_target_is_never_pruned_whatever_the_declaration_order(
    declared_order: tuple[str, str], link: str, target: str, tmp_path: Path
) -> None:
    """Regression (section 5.4.3): ``max`` kept the first deepest holder, so order decided."""
    repo = tmp_path / "repo"
    link_path, target_dir = _link_root(repo, link, target)
    skill_md = _write_skill_md(target_dir / "demo")
    locations = OutputLocations.declared([f"{rel}/" for rel in declared_order], repo)

    skill_md.unlink()
    locations.prune_emptied([skill_md], repo)

    assert not (target_dir / "demo").exists()
    assert target_dir.is_dir() and not target_dir.is_symlink()
    assert link_path.is_symlink() and link_path.resolve() == target_dir.resolve()


def test_unlinked_declared_root_is_pruned_once_empty(tmp_path: Path) -> None:
    """With no links, an emptied declared root goes and its parent stays (today's rule)."""
    repo = tmp_path / "repo"
    skill_md = _write_skill_md(repo / _AGENTS_SKILLS / "demo")
    locations = OutputLocations.declared([f"{_AGENTS_SKILLS}/"], repo)

    skill_md.unlink()
    locations.prune_emptied([skill_md], repo)

    assert not (repo / _AGENTS_SKILLS).exists()
    assert (repo / ".agents").is_dir()


def test_retired_location_bounds_deletion_like_a_current_one(tmp_path: Path) -> None:
    """A retired root (``shared_skills/``) is a directory bound, not a name prefix."""
    locations = OutputLocations.declared(("shared_skills/",), tmp_path)

    assert locations.contains("shared_skills/x/SKILL.md")
    assert not locations.contains("shared_skillsx/a")


@needs_posix_symlinks
def test_symlink_loop_in_a_declared_root_neither_raises_nor_prunes(tmp_path: Path) -> None:
    """Regression: ``Path.resolve()`` raises ``RuntimeError`` on a symlink loop on 3.12."""
    repo = tmp_path / "repo"
    (repo / ".agents").mkdir(parents=True)
    (repo / _AGENTS_SKILLS).symlink_to("skills")  # .agents/skills -> .agents/skills

    locations = OutputLocations.declared([f"{_AGENTS_SKILLS}/"], repo)
    locations.prune_emptied([repo / _AGENTS_SKILLS / "demo" / "SKILL.md"], repo)

    assert locations.contains(f"{_AGENTS_SKILLS}/demo/SKILL.md")
    assert (repo / _AGENTS_SKILLS).is_symlink()
