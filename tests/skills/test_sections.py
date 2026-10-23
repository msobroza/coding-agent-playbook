"""``skills.sections``: the sections a skill's ``playbook:`` block declares (prU D17, D47)."""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.artifacts.impact import IMPACT_BANDS, Impact
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.skills.sections import (
    SkillSection,
    declared_sections_value,
    one_line_phrase_problem,
    section_list_problems,
    section_rank,
    skill_sections,
)

_MOCKING = {
    "id": "mocking",
    "title": "Mocking",
    "impact": "CRITICAL",
    "summary": "Fakes at the boundary.",
    "open_when": "Replacing a collaborator in a test.",
}
_FIXTURES = {
    "id": "fixtures",
    "title": "Fixtures",
    "impact": "MEDIUM",
    "summary": "Shared setup.",
    "open_when": "Adding or sharing test setup.",
}


def _skill(block: Any) -> Skill:
    return Skill({"id": "python-testing", "playbook": block}, "# Body\n", None, None, "pkg")


def test_skill_sections_reads_each_declared_section_in_order() -> None:
    sections = skill_sections(_skill({"sections": [_MOCKING, _FIXTURES]}))

    assert sections == (
        SkillSection(
            "mocking",
            "Mocking",
            Impact.CRITICAL,
            "Fakes at the boundary.",
            "Replacing a collaborator in a test.",
        ),
        SkillSection(
            "fixtures", "Fixtures", Impact.MEDIUM, "Shared setup.", "Adding or sharing test setup."
        ),
    )


def test_a_skill_without_sections_has_none() -> None:
    assert skill_sections(_skill({"use_when": "testing"})) == ()
    assert skill_sections(Skill({"id": "plain"}, "", None, None, "pkg")) == ()


@pytest.mark.parametrize(
    "sections",
    [
        "mocking",
        [],
        [{**_MOCKING, "impact": "URGENT"}],
        [{**_MOCKING, "extra": "x"}],
        [{key: value for key, value in _MOCKING.items() if key != "open_when"}],
        [{**_MOCKING, "title": 42}],
        [_MOCKING, "fixtures"],
        [_MOCKING, {**_FIXTURES, "id": "mocking"}],
    ],
)
def test_a_malformed_sections_list_reads_as_no_sections(sections: object) -> None:
    assert skill_sections(_skill({"sections": sections})) == ()


def test_sections_keep_their_declared_order_even_when_misordered() -> None:
    # S2 reports the order; parsing never reorders what the author wrote.
    sections = skill_sections(_skill({"sections": [_FIXTURES, _MOCKING]}))

    assert [section.id for section in sections] == ["fixtures", "mocking"]


def test_a_malformed_playbook_block_reads_as_no_sections() -> None:
    assert skill_sections(_skill("yes")) == ()


@pytest.mark.parametrize(
    ("impact", "low", "high"),
    [
        (Impact.CRITICAL, 20, 39),
        (Impact.HIGH, 40, 59),
        (Impact.MEDIUM, 60, 79),
        (Impact.LOW, 80, 99),
    ],
)
def test_each_impact_owns_its_priority_band(impact: Impact, low: int, high: int) -> None:
    band = IMPACT_BANDS[impact]

    assert (band[0], band[-1]) == (low, high)
    assert impact.band == band


def test_impacts_are_declared_from_critical_to_low() -> None:
    assert list(Impact) == [Impact.CRITICAL, Impact.HIGH, Impact.MEDIUM, Impact.LOW]
    assert [impact.rank for impact in Impact] == [0, 1, 2, 3]


def test_an_empty_sections_list_declares_no_sections() -> None:
    assert declared_sections_value(_skill({"sections": []})) is None
    assert declared_sections_value(_skill({"use_when": "testing"})) is None
    assert declared_sections_value(_skill({"sections": "x"})) == "x"


def test_section_list_problems_reports_a_non_list_then_entries_then_duplicates() -> None:
    assert section_list_problems("mocking") == [
        "'playbook.sections' must be a list of mappings with keys id, title, impact, summary, "
        "open_when, got str 'mocking'"
    ]
    assert section_list_problems([_MOCKING, "fixtures"]) == [
        "section entry 2 of 'playbook.sections': must be a mapping with keys id, title, "
        "impact, summary, open_when, got str 'fixtures'"
    ]
    assert section_list_problems([_MOCKING, _MOCKING]) == [
        "'playbook.sections' declares section 'mocking' more than once; ids are unique"
    ]
    assert section_list_problems([_MOCKING, _FIXTURES]) == []


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (None, "is missing 'open_when'"),
        (" ", "'open_when' must be a non-empty string, got str ' '"),
        (3, "'open_when' must be a non-empty string, got int 3"),
        ("a\nb", "'open_when' must be one line, got 'a\\nb'"),
        ("Editing a model.", None),
    ],
)
def test_one_line_phrase_problem(value: object, problem: str | None) -> None:
    assert one_line_phrase_problem("open_when", value) == problem


def test_section_rank_puts_none_and_undeclared_ids_in_other_last() -> None:
    sections = [
        SkillSection("mocking", "Mocking", Impact.CRITICAL, "S.", "O."),
        SkillSection("fixtures", "Fixtures", Impact.HIGH, "S.", "O."),
    ]
    rank = section_rank(sections)

    assert [rank("mocking"), rank("fixtures")] == [0, 1]
    assert [rank(None), rank("team-extra")] == [2, 2]
