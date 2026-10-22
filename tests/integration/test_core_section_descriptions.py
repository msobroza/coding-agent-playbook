"""Core skills' sections fit the description budget (prU D17, D18, L0-15).

A sectioned skill's Covers clause names its active sections and never
truncates, so its description must fit :data:`DESCRIPTION_MAX_CHARS` even when
every declared section is active. The section ids are pinned in the order each
skill's mapping (``specs/prU-core-python-skills/mapping-<skill>.md``) gives them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.skills.document import (
    DESCRIPTION_MAX_CHARS,
    sectioned_description,
    skill_catalog_block,
)
from coding_agent_playbook.skills.membership import is_rule_skill
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.skills.sections import skill_sections
from tests._catalog import core_skills

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.skill import Skill

pytestmark = pytest.mark.catalog

#: Core skills that take member rules, by id.
RULE_SKILLS: Final = {skill_id_of(skill): skill for skill in core_skills() if is_rule_skill(skill)}

#: Section ids in mapping order, for the skills whose sections are declared.
MAPPED_SECTION_IDS: Final = {
    "python-coding": (
        "errors",
        "shape",
        "types",
        "effects",
        "async",
        "pydantic",
        "classes",
        "functions",
        "idioms",
    ),
    "python-tooling": (
        "linting",
        "type-checking",
        "formatting",
        "test-configuration",
        "package-management",
    ),
    "web-application": (
        "security",
        "database",
        "async-io",
        "api-design",
        "app-structure",
        "observability",
        "testing",
        "api-conventions",
    ),
}


def _full_description(skill: Skill) -> str:
    """``skill``'s description with a Covers clause naming every declared section."""
    titles = [section.title for section in skill_sections(skill)]
    use_when = skill_catalog_block(skill).use_when
    return sectioned_description(str(skill.frontmatter["description"]), titles, use_when)


@pytest.mark.parametrize("skill_id", sorted(RULE_SKILLS))
def test_description_with_every_declared_section_fits(skill_id: str) -> None:
    text = _full_description(RULE_SKILLS[skill_id])
    assert len(text) <= DESCRIPTION_MAX_CHARS, f"{skill_id}: {len(text)} chars: {text!r}"


@pytest.mark.parametrize("skill_id", sorted(MAPPED_SECTION_IDS))
def test_skill_declares_the_mapping_sections_in_order(skill_id: str) -> None:
    declared = tuple(section.id for section in skill_sections(RULE_SKILLS[skill_id]))
    assert declared == MAPPED_SECTION_IDS[skill_id]
