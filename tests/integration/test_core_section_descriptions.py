"""Core skills' sections fit the description budget (prU D17, D18, L0-15).

A sectioned skill's Covers clause names its active sections and never
truncates, so its description must fit :data:`DESCRIPTION_MAX_CHARS` even when
every declared section is active. Each skill's pins module pins its section
ids in the order its mapping gives them (``CoreSkillPins.section_ids``).
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
from tests.core_skill_pins import ALL_PINS

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.skill import Skill
    from tests.core_skill_pins import CoreSkillPins

pytestmark = pytest.mark.catalog

#: Core skills that take member rules, by id.
RULE_SKILLS: Final = {skill_id_of(skill): skill for skill in core_skills() if is_rule_skill(skill)}


def _full_description(skill: Skill) -> str:
    """``skill``'s description with a Covers clause naming every declared section."""
    titles = [section.title for section in skill_sections(skill)]
    use_when = skill_catalog_block(skill).use_when
    return sectioned_description(str(skill.frontmatter["description"]), titles, use_when)


@pytest.mark.parametrize("skill_id", sorted(RULE_SKILLS))
def test_description_with_every_declared_section_fits(skill_id: str) -> None:
    text = _full_description(RULE_SKILLS[skill_id])
    assert len(text) <= DESCRIPTION_MAX_CHARS, f"{skill_id}: {len(text)} chars: {text!r}"


@pytest.mark.parametrize("pins", ALL_PINS, ids=lambda pins: pins.skill_id)
def test_skill_declares_the_mapping_sections_in_order(pins: CoreSkillPins) -> None:
    declared = tuple(section.id for section in skill_sections(RULE_SKILLS[pins.skill_id]))
    assert declared == pins.section_ids
