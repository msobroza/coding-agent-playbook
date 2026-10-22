"""agent_harness writes member rules inside their skill (prU D22, D5, D46.7).

A scoped rule whose skill is emitted lands at ``skills/<skill>/rules/<id>.md``
(description frontmatter, sentinel, rendered body); one whose skill is not
emitted keeps the root ``references/<id>.md``. The manifest records the path,
the rule's ``section`` and, for a rule placed by location, no ``skill`` (the
path names it). The skill's ``SKILL.md`` keeps its authored description and
gets the generated rules index the other skill trees carry.
Split from ``test_adapter.py``, which is already over 800 lines.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.manifest import read_manifest
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from tests.member_skill_samples import (
    SAMPLE_PLAYBOOK_BLOCK,
    sample_member_reference,
    sample_member_skill,
)

if TYPE_CHECKING:
    from pathlib import Path


def _member_rule(
    rule_id: str = "python-typing",
    *,
    skill: str | None = "python-coding",
    section: str | None = None,
    from_location: bool = False,
) -> Rule:
    body = "# Python typing\n\nUse type hints.\n"
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name="Typing",
        description="Prefer a concrete type.",
        scope="scoped",
        globs=["**/*.py"],
        priority=50,
        skill=skill,
        section=section,
    )
    home = skill if from_location else None
    return Rule(frontmatter, body, body, False, None, "test", home, from_location)


def _emit(tmp_path: Path, *rules: Rule, with_skill: bool = True) -> None:
    adapter = AgentHarnessAdapter()
    if with_skill:
        skill = sample_member_skill("python-coding", sample_member_reference("python-typing"))
        adapter.write_skill(skill, tmp_path)
    for rule in rules:
        adapter.write_rule(rule, tmp_path)
    adapter.finalize(tmp_path)


def test_member_rule_is_written_inside_its_emitted_skill(tmp_path: Path) -> None:
    _emit(tmp_path, _member_rule())

    target = tmp_path / "skills" / "python-coding" / "rules" / "python-typing.md"
    assert target.read_text(encoding="utf-8") == (
        "---\ndescription: Prefer a concrete type.\n---\n"
        f"{sentinel_line('html')}\n\n# Python typing\n\nUse type hints.\n"
    )


def test_tree_has_no_root_references_when_every_scoped_rule_is_a_member(tmp_path: Path) -> None:
    _emit(tmp_path, _member_rule())

    assert not (tmp_path / "references").exists()
    harness_md = (tmp_path / "HARNESS.md").read_text(encoding="utf-8")
    assert "references/" not in harness_md


def test_member_of_a_skill_not_emitted_stays_in_root_references(tmp_path: Path) -> None:
    _emit(tmp_path, _member_rule(), with_skill=False)

    assert (tmp_path / "references" / "python-typing.md").is_file()
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["references/python-typing.md"]
    assert (entry.kind, entry.scope, entry.skill) == ("rule", "scoped", "python-coding")


def test_manifest_records_the_in_skill_path_and_section(tmp_path: Path) -> None:
    _emit(tmp_path, _member_rule(section="typing", from_location=True))

    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["skills/python-coding/rules/python-typing.md"]
    # The location names the skill, so the entry records none (like the source file).
    assert (entry.kind, entry.section, entry.skill) == ("rule", "typing", None)


def test_manifest_keeps_an_authored_skill_of_a_joining_rule(tmp_path: Path) -> None:
    _emit(tmp_path, _member_rule())

    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["skills/python-coding/rules/python-typing.md"]
    assert entry.skill == "python-coding"


def test_skill_md_keeps_authored_description_and_gets_the_rules_index(tmp_path: Path) -> None:
    skill = sample_member_skill("python-coding", sample_member_reference("python-typing"))
    adapter = AgentHarnessAdapter()
    adapter.write_skill(skill, tmp_path)

    adapter.finalize(tmp_path)

    skill_md = tmp_path / "skills" / "python-coding" / "SKILL.md"
    frontmatter, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert frontmatter["description"] == skill.frontmatter["description"]  # authored, not composed
    assert body.endswith(
        "## Rules\n\n"
        "Each file under rules/ is one rule. Open only the ones the current task needs.\n\n"
        "- [python-typing](rules/python-typing.md) — Typing: "
        "Prefer a concrete type or a Protocol to Any.\n"
    )
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["skills/python-coding/SKILL.md"]
    assert entry.body == skill.body  # the authored body, index-free, for the import
    assert entry.extra_frontmatter["playbook"] == SAMPLE_PLAYBOOK_BLOCK  # restored on import


def test_rule_without_skill_records_no_skill(tmp_path: Path) -> None:
    """Regression: a rule without ``skill`` keeps the manifest entry it had before."""
    _emit(tmp_path, _member_rule(skill=None))

    manifest = read_manifest(tmp_path)
    assert manifest is not None
    entry = manifest.index_by_path()["references/python-typing.md"]
    assert (entry.skill, entry.section) == (None, None)


def test_an_unsectioned_rule_entry_has_no_section_key(tmp_path: Path) -> None:
    """Regression: ``section`` is emitted only when set, so old manifests stay byte-identical."""
    _emit(tmp_path, dataclasses.replace(_member_rule(), home_skill=None))

    manifest_text = (tmp_path / ".playbook" / "manifest.toml").read_text(encoding="utf-8")
    assert "section" not in manifest_text
