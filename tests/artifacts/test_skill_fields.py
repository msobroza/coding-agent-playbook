"""The skill-membership fields of the canonical types (specs/prS-skills-context.md 6.8.1).

``RuleFrontmatter.skill`` names the skill whose references deliver a scoped rule;
``Skill.member_references`` holds the rendered member rules ``compose_skills``
attaches at sync. Both must round-trip, and neither may change what a rule or
skill written before them serializes to. Kept apart from ``test_artifacts.py`` for
the file-size budget.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from coding_agent_playbook.artifacts.impact import Impact
from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import ListedReference, Skill
from coding_agent_playbook.catalog.source import FileSystemArtifactSource

_TYPING_RULE_MD = """\
---
id: python-typing
name: Typing
description: Prefer a concrete type to Any.
scope: scoped
skill: python-coding
globs:
- '**/*.py'
priority: 50
---
# Python typing conventions
"""


def _rule(*, skill: str | None) -> Rule:
    frontmatter = RuleFrontmatter(
        id="python-typing",
        name="Typing",
        description="Prefer a concrete type to Any.",
        scope="scoped",
        globs=["**/*.py"],
        skill=skill,
    )
    return Rule(frontmatter, "# Body\n", "# Body\n", False, Path("rules/typing.md"), "pkg")


def test_rule_frontmatter_skill_defaults_to_none_and_round_trips(tmp_path: Path) -> None:
    default = RuleFrontmatter(id="x", name="X", description="d", scope="always")
    assert default.skill is None
    rule = _rule(skill="python-coding")
    assert Rule.from_dict(rule.to_dict()) == rule
    path = tmp_path / "typing.md"
    path.write_text(_TYPING_RULE_MD, encoding="utf-8")
    parsed = Rule.from_markdown(path, "pkg")
    assert parsed.frontmatter.skill == "python-coding"
    path.write_text(parsed.to_markdown(), encoding="utf-8")
    assert Rule.from_markdown(path, "pkg") == parsed


def test_rule_without_skill_markdown_is_byte_identical() -> None:
    assert _rule(skill=None).to_markdown() == (
        "---\n"
        "id: python-typing\n"
        "name: Typing\n"
        "description: Prefer a concrete type to Any.\n"
        "scope: scoped\n"
        "globs:\n"
        "- '**/*.py'\n"
        "priority: 50\n"
        "---\n"
        "# Body\n"
    )


def _member(
    rule_id: str = "python-typing", *, globs: tuple[str, ...] = ("**/*.py",)
) -> MemberReference:
    return MemberReference(
        rule_id=rule_id,
        name="Typing",
        description="Prefer a concrete type to Any.",
        priority=50,
        globs=globs,
        text="*Rule `python-typing`.*\n\n# Body\n",
        source_package="coding_agent_playbook",
    )


def _skill_dict() -> dict[str, Any]:
    """A ``Skill.to_dict()`` payload as engines before member references wrote it."""
    return {
        "frontmatter": {"id": "python-coding", "description": "Python conventions."},
        "body": "# Python coding\n",
        "scripts_dir": None,
        "references_dir": None,
        "source_package": "coding_agent_playbook",
    }


def test_skill_member_references_round_trip_through_dict() -> None:
    skill = Skill.from_dict(_skill_dict())
    composed = dataclasses.replace(
        skill, member_references=(_member(), _member("pytest", globs=()))
    )
    data = composed.to_dict()
    assert data["member_references"][0]["globs"] == ["**/*.py"]
    assert Skill.from_dict(data) == composed


def test_skill_from_dict_accepts_dict_without_member_references() -> None:
    skill = Skill.from_dict(_skill_dict())
    assert skill.member_references == ()
    assert skill.frontmatter == {"id": "python-coding", "description": "Python conventions."}


def test_member_reference_round_trips_and_names_its_file() -> None:
    member = _member()
    assert member.filename == "python-typing.md"
    assert MemberReference.from_dict(member.to_dict()) == member


def test_a_sectioned_member_keeps_its_impact_as_the_enum_through_dict() -> None:
    member = dataclasses.replace(_member(), section="types", impact=Impact.HIGH)
    data = member.to_dict()

    assert (data["section"], data["impact"]) == ("types", "HIGH")
    restored = MemberReference.from_dict(data)
    assert restored == member
    assert restored.impact is Impact.HIGH


def test_listed_references_round_trip_through_their_own_dict() -> None:
    ref = ListedReference("references/guide.md", "Choosing a fake.")
    skill = dataclasses.replace(Skill.from_dict(_skill_dict()), listed_references=(ref,))

    assert ref.to_dict() == {"path": "references/guide.md", "open_when": "Choosing a fake."}
    assert ListedReference.from_dict(ref.to_dict()) == ref
    assert Skill.from_dict(skill.to_dict()) == skill
    assert Skill.from_dict(_skill_dict()).listed_references == ()


def test_skill_source_dir_round_trips_and_defaults_to_none() -> None:
    skill = Skill({"id": "x"}, "", None, None, "pkg", source_dir=Path("catalog/core/skills/x"))

    assert Skill.from_dict(skill.to_dict()) == skill
    assert Skill.from_dict(_skill_dict()).source_dir is None


def test_the_catalog_source_records_each_skills_directory(tmp_path: Path) -> None:
    skill_dir = tmp_path / "playbook" / "skills" / "risk-models"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nid: risk-models\n---\nBody\n", encoding="utf-8")

    skills = FileSystemArtifactSource(repo_root=tmp_path).list_skills()

    by_id = {skill.frontmatter.get("id"): skill for skill in skills}
    assert by_id["risk-models"].source_dir == skill_dir
