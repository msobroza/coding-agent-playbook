"""The skill-membership fields of the canonical types (specs/prS-skills-context.md 6.8.1).

``RuleFrontmatter.skill`` names the skill whose references deliver a scoped rule;
``Skill.member_references`` holds the rendered member rules ``compose_skills``
attaches at sync. Both must round-trip, and neither may change what a rule or
skill written before them serializes to. Kept apart from ``test_types.py`` for
the file-size budget.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from coding_agent_playbook._member_reference import MemberReference
from coding_agent_playbook.types import Rule, RuleFrontmatter, Skill

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
        "version: 1\n"
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
