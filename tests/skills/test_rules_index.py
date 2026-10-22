"""The rules index of a skill that declares sections (prU D17, D42, D47, D58).

A sectioned skill's ``SKILL.md`` gets, after its authored body, the fixed "How
to use this skill" paragraph, a ``## Rules`` index grouped by section (one
``### <title> [<IMPACT>]`` heading per section with an active member, its
summary and open-when line, then a two-column table), and a "References and
examples" list. Sectionless skills keep the flat index. Expected texts are
written out in full, so a test can disagree with the code.
"""

from __future__ import annotations

from typing import Any

from coding_agent_playbook.artifacts.impact import Impact
from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.artifacts.skill import ListedReference, Skill
from coding_agent_playbook.skills.document import emitted_body

HOW_TO_USE = (
    "## How to use this skill\n\n"
    "The index below lists only the rules that apply to this repository, most important "
    "first. Find the sections whose open-when line matches the change, then read those "
    "rules in full before editing; usually one to three are enough. Open a reference or "
    "example when a rule names it or its open-when line matches the change.\n\n"
)
RULES_LEAD = (
    "## Rules\n\nEach file under rules/ is one rule. Open only the ones the current task needs.\n\n"
)
TABLE_HEAD = "| Rule | Requires |\n| --- | --- |\n"

SECTIONS: list[dict[str, str]] = [
    {
        "id": "mocking",
        "title": "Mocking",
        "impact": "CRITICAL",
        "summary": "Double only what the code does not own.",
        "open_when": "A test stands in for a collaborator.",
    },
    {
        "id": "fixtures",
        "title": "Fixtures",
        "impact": "HIGH",
        "summary": "Share setup without hiding it.",
        "open_when": "A fixture or conftest.py is added or changed.",
    },
    {
        "id": "coverage",
        "title": "Coverage",
        "impact": "MEDIUM",
        "summary": "Find the inputs the suite still misses.",
        "open_when": "Deciding which cases to add.",
    },
]


def _member(
    rule_id: str,
    section: str | None,
    impact: str | None,
    *,
    priority: int = 20,
    name: str | None = None,
    description: str | None = None,
) -> MemberReference:
    return MemberReference(
        rule_id,
        name or rule_id.title(),
        description or f"{rule_id} description.",
        priority,
        ("tests/**",),
        "text\n",
        "pkg",
        section=section,
        impact=None if impact is None else Impact(impact),
    )


def _skill(
    *members: MemberReference,
    references: tuple[ListedReference, ...] = (),
    playbook: dict[str, Any] | None = None,
) -> Skill:
    block: dict[str, Any] = {"use_when": "editing tests", "sections": SECTIONS}
    frontmatter = {
        "id": "python-testing",
        "name": "python-testing",
        "description": "Test conventions.",
        "playbook": playbook if playbook is not None else block,
    }
    return Skill(
        frontmatter,
        "# Python testing\n\nIntro.\n",
        None,
        None,
        "pkg",
        members,
        listed_references=references,
    )


def test_sectioned_index_groups_members_under_their_section_headings() -> None:
    body = emitted_body(
        _skill(
            _member("mock-autospec", "mocking", "CRITICAL", priority=20),
            _member("mock-boundary", "mocking", "CRITICAL", priority=21),
            _member("fixture-scope", "fixtures", "HIGH", priority=40),
        )
    )
    assert body == (
        "# Python testing\n\nIntro.\n\n"
        f"{HOW_TO_USE}{RULES_LEAD}"
        "### Mocking [CRITICAL]\n\n"
        "Double only what the code does not own.\n\n"
        "Open when: A test stands in for a collaborator.\n\n"
        f"{TABLE_HEAD}"
        "| [mock-autospec](rules/mock-autospec.md) | Mock-Autospec: mock-autospec description. |\n"
        "| [mock-boundary](rules/mock-boundary.md) | Mock-Boundary: mock-boundary description. |\n"
        "\n"
        "### Fixtures [HIGH]\n\n"
        "Share setup without hiding it.\n\n"
        "Open when: A fixture or conftest.py is added or changed.\n\n"
        f"{TABLE_HEAD}"
        "| [fixture-scope](rules/fixture-scope.md) | Fixture-Scope: fixture-scope description. |\n"
    )


def test_a_section_without_an_active_member_is_left_out() -> None:
    body = emitted_body(_skill(_member("coverage-branches", "coverage", "MEDIUM", priority=60)))
    assert "### Mocking" not in body
    assert "### Fixtures" not in body
    assert "### Coverage [MEDIUM]\n" in body


def test_table_cells_escape_pipes_and_stay_on_one_line() -> None:
    body = emitted_body(
        _skill(
            _member(
                "mock-autospec",
                "mocking",
                "CRITICAL",
                name="Autospec | spec",
                description="Use create_autospec\nwith spec_set | instance=True.",
            )
        )
    )
    assert (
        "| [mock-autospec](rules/mock-autospec.md) | Autospec \\| spec: Use create_autospec "
        "with spec_set \\| instance=True. |\n"
    ) in body


def test_members_from_another_layer_without_a_section_render_last_under_other() -> None:
    body = emitted_body(
        _skill(
            _member("fixture-scope", "fixtures", "HIGH", priority=40),
            _member("team-mocks", None, None, priority=10),
        )
    )
    headings = [line for line in body.splitlines() if line.startswith("### ")]
    assert headings == ["### Fixtures [HIGH]", "### Other"]
    assert body.endswith(
        "### Other\n\n"
        "Rules from other layers that name no section of this skill.\n\n"
        f"{TABLE_HEAD}"
        "| [team-mocks](rules/team-mocks.md) | Team-Mocks: team-mocks description. |\n"
    )


def test_references_and_examples_follow_the_rules_index() -> None:
    references = (
        ListedReference("references/mocking-guide.md", "Choosing between a fake and a mock."),
        ListedReference("examples/booking-api", "Copying a whole test layout."),
    )
    body = emitted_body(
        _skill(_member("mock-autospec", "mocking", "CRITICAL"), references=references)
    )
    assert body.endswith(
        "## References and examples\n\n"
        "- [references/mocking-guide.md](references/mocking-guide.md) — Open when: Choosing "
        "between a fake and a mock.\n"
        "- [examples/booking-api](examples/booking-api) — Open when: Copying a whole test "
        "layout.\n"
    )
    assert body.index("## Rules") < body.index("## References and examples")


def test_a_sectionless_skill_keeps_the_flat_index() -> None:
    playbook = {"use_when": "editing tests"}
    body = emitted_body(_skill(_member("pytest", None, None, priority=50), playbook=playbook))
    assert body == (
        "# Python testing\n\nIntro.\n\n"
        f"{RULES_LEAD}"
        "- [pytest](rules/pytest.md) — Pytest: pytest description.\n"
    )
