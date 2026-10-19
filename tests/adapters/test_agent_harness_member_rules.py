"""agent_harness keeps its layout for member rules (specs/prS-skills-context.md 6.4.9, 6.8.7).

A scoped rule stays at the harness root ``references/<id>.md`` and its
``skill`` is recorded in the manifest only (E5). A composed skill is written
with its authored description and body and no member reference files, so a
lossless import never mistakes a rendered member for a hand-written reference.
Split from ``test_agent_harness.py``, which is already over 800 lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.manifest import read_manifest
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from tests.member_skill_samples import (
    SAMPLE_PLAYBOOK_BLOCK,
    sample_member_reference,
    sample_member_skill,
)

if TYPE_CHECKING:
    from pathlib import Path


def _member_rule(rule_id: str = "python-typing", *, skill: str | None = "python-coding") -> Rule:
    body = "# Python typing\n\nUse type hints.\n"
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name="Typing",
        description="Prefer a concrete type.",
        scope="scoped",
        globs=["**/*.py"],
        priority=50,
        skill=skill,
    )
    return Rule(frontmatter, body, body, False, None, "test")


def test_scoped_rule_stays_in_root_references_with_skill_in_manifest(tmp_path: Path) -> None:
    adapter = AgentHarnessAdapter()
    adapter.write_rule(_member_rule(), tmp_path)

    adapter.finalize(tmp_path)

    assert (tmp_path / "references" / "python-typing.md").is_file()
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["references/python-typing.md"]
    assert (entry.kind, entry.scope, entry.skill) == ("rule", "scoped", "python-coding")


def test_skill_dir_gets_no_member_reference_files(tmp_path: Path) -> None:
    skill = sample_member_skill("python-coding", sample_member_reference("python-typing"))
    adapter = AgentHarnessAdapter()
    adapter.write_skill(skill, tmp_path)

    adapter.finalize(tmp_path)

    skill_dir = tmp_path / "skills" / "python-coding"
    assert sorted(p.relative_to(skill_dir).as_posix() for p in skill_dir.rglob("*")) == ["SKILL.md"]
    frontmatter, body = split_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    assert frontmatter["description"] == skill.frontmatter["description"]  # authored, not composed
    assert "## References" not in body
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["skills/python-coding/SKILL.md"]
    assert entry.extra_frontmatter["playbook"] == SAMPLE_PLAYBOOK_BLOCK  # restored on import


def test_rule_without_skill_records_no_skill(tmp_path: Path) -> None:
    """Regression: a rule without ``skill`` keeps the manifest entry it had before."""
    adapter = AgentHarnessAdapter()
    adapter.write_rule(_member_rule(skill=None), tmp_path)

    adapter.finalize(tmp_path)

    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.index_by_path()["references/python-typing.md"].skill is None
