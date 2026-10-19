"""``WhereGuidanceBuffer``: the Where entries a composite adapter collects (specs/prS-skills-context.md 6.4.6)."""

from __future__ import annotations

from coding_agent_playbook.adapters._where_guidance import WhereGuidanceBuffer
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.skills.document import WhereEntry, where_guidance_section
from tests.member_skill_samples import sample_member_reference, sample_member_skill

_RULE_SECTION = "## Project context\n\nAsk first.\n\n---\n"


def _plain_skill() -> Skill:
    frontmatter = {"id": "brainstorming", "name": "brainstorming", "description": "Ideas."}
    return Skill(frontmatter, "# Brainstorming\n", None, None, "superpowers")


def test_after_returns_the_sections_alone_without_entries() -> None:
    buffer = WhereGuidanceBuffer()
    buffer.add(_plain_skill())

    assert buffer.after([_RULE_SECTION]) == [_RULE_SECTION]
    assert buffer.after([]) == []


def test_after_appends_one_section_sorted_by_skill_id_with_each_skill_once() -> None:
    ml_data = sample_member_skill("ml-data", sample_member_reference("ml-serialization"))
    ml_data.frontmatter["playbook"]["files"] = "Model code"
    python_coding = sample_member_skill("python-coding", sample_member_reference())
    buffer = WhereGuidanceBuffer()
    for skill in (python_coding, ml_data, python_coding):
        buffer.add(skill)

    expected = where_guidance_section(
        [WhereEntry("ml-data", "Model code"), WhereEntry("python-coding", "Any Python file")]
    )
    assert buffer.after([_RULE_SECTION]) == [_RULE_SECTION, expected]


def test_a_skill_without_members_adds_no_entry() -> None:
    no_members = sample_member_skill("python-coding")
    buffer = WhereGuidanceBuffer()
    buffer.add(no_members)

    assert buffer.after([]) == []
