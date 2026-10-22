"""Composition of a skill that declares sections (prU D17, D42, D47, D58).

``compose_skills`` places each active member in its section (``section`` and
``impact`` on its :class:`MemberReference`), orders members by section, then
priority, then id, with members that name no declared section last (D42), and
lists the ``playbook.references`` entries whose ``applies_if`` passes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import ListedReference, Skill
from coding_agent_playbook.skills.membership import compose_skills

SECTIONS = [
    {
        "id": "mocking",
        "title": "Mocking",
        "impact": "CRITICAL",
        "summary": "Fakes at the boundary.",
        "open_when": "A test replaces a collaborator.",
    },
    {
        "id": "fixtures",
        "title": "Fixtures",
        "impact": "HIGH",
        "summary": "Visible setup.",
        "open_when": "A fixture changes.",
    },
]


def _rule(rule_id: str, section: str | None, priority: int) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id,
        description=f"{rule_id}.",
        scope="scoped",
        globs=["tests/**"],
        priority=priority,
        skill="python-testing",
        section=section,
    )
    return Rule(frontmatter, "# r\n", "# r\n", False, Path(f"{rule_id}.md"), "pkg")


def _skill(**extra: Any) -> Skill:
    block: dict[str, Any] = {"use_when": "editing tests", "sections": SECTIONS, **extra}
    frontmatter = {"id": "python-testing", "description": "Tests.", "playbook": block}
    return Skill(frontmatter, "# Body\n", None, None, "pkg")


def test_members_sort_by_section_order_then_priority_with_other_last() -> None:
    rules = [
        _rule("fixture-scope", "fixtures", 40),
        _rule("team-extra", None, 10),
        _rule("mock-boundary", "mocking", 21),
        _rule("mock-autospec", "mocking", 21),
        _rule("mock-faithful", "mocking", 20),
    ]
    [composed] = compose_skills([_skill()], rules, rules)
    placed = [(m.rule_id, m.section, m.impact) for m in composed.member_references]
    assert placed == [
        ("mock-faithful", "mocking", "CRITICAL"),
        ("mock-autospec", "mocking", "CRITICAL"),
        ("mock-boundary", "mocking", "CRITICAL"),
        ("fixture-scope", "fixtures", "HIGH"),
        ("team-extra", None, None),
    ]


def test_members_of_a_sectionless_skill_carry_no_section() -> None:
    rule = _rule("pytest", None, 50)
    skill = Skill({"id": "python-testing", "playbook": {"use_when": "x"}}, "", None, None, "pkg")
    [composed] = compose_skills([skill], [rule], [rule])
    member = composed.member_references[0]
    assert (member.section, member.impact) == (None, None)


def test_listed_references_are_the_entries_whose_applies_if_passes() -> None:
    references = [
        {"path": "references/guide.md", "open_when": "Choosing a fake."},
        {
            "path": "examples/booking-api",
            "open_when": "Copying a test layout.",
            "applies_if": {"any_framework": ["fastapi"]},
        },
        {
            "path": "references/django.md",
            "open_when": "Testing Django views.",
            "applies_if": {"any_framework": ["django"]},
        },
    ]
    rules = [_rule("mock-faithful", "mocking", 20)]
    [composed] = compose_skills(
        [_skill(references=references)],
        rules,
        rules,
        reference_applies=lambda predicate: predicate == {"any_framework": ["fastapi"]},
    )
    assert composed.listed_references == (
        ListedReference("references/guide.md", "Choosing a fake."),
        ListedReference("examples/booking-api", "Copying a test layout."),
    )
