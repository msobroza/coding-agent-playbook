"""What a probe repo must emit for each core skill it activates (D5, D13; prU D59, D63).

A core skill is checked on the probe its pins name (``CoreSkillPins.probe``): the
reference probe, or the Domino probe for the Domino skills the reference probe
never activates. ``tests/integration/test_core_skills.py`` runs these checks on
both probes, so each probe's tests stay one line.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters.claude_code.paths import CLAUDE_RULES_PATH
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._catalog import CORE_SKILLS_ROOT, core_rules

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from tests.core_skill_pins import CoreSkillPins

#: The truncation tail of a Covers clause too long for the description budget.
_TRUNCATION_TAIL: Final = re.compile(r"and \d+ more")


def authored_skill_md(skill_id: str) -> tuple[dict[str, object], str]:
    """The authored ``SKILL.md`` of core skill ``skill_id``: (frontmatter, body)."""
    path = CORE_SKILLS_ROOT / skill_id / "SKILL.md"
    return split_frontmatter(path.read_text(encoding="utf-8"))


def _probe_members(pins: CoreSkillPins) -> list[Rule]:
    """The members of ``pins``' skill that its own probe activates."""
    return [
        rule
        for rule in core_rules().values()
        if rule.frontmatter.skill == pins.skill_id
        and rule.frontmatter.id not in pins.probe_inactive
    ]


def _assert_covers_clause(skill_id: str, description: str, members: list[Rule]) -> None:
    """The Covers clause names the active sections, or every active member's name."""
    block = authored_skill_md(skill_id)[0]["playbook"]
    assert isinstance(block, dict)
    if not block.get("sections"):
        for rule in members:
            assert rule.frontmatter.name in description, (
                f"{skill_id} omits {rule.frontmatter.name!r}"
            )
        return
    # A sectioned skill's Covers clause names its active sections, not its members (D17).
    covers = description.partition(" Covers ")[2].partition(". Use when ")[0].lower()
    # Only declared sections are named: a member in D42's Other adds no name. A title
    # may hold commas ("Names, types, docs"), so each title is looked up, not counted.
    declared = {section["id"] for section in block["sections"]}
    active = {rule.frontmatter.section for rule in members} & declared
    named = {s["id"] for s in block["sections"] if str(s["title"]).lower() in covers}
    assert named == active, f"{skill_id} covers {covers!r}"


def assert_emitted_within_budget(repo: Path, pins: CoreSkillPins) -> None:
    """``repo``'s emitted skill: description shape and budget, an index of its probe members."""
    skill_id = pins.skill_id
    skill_md = repo / ".claude" / "skills" / skill_id / "SKILL.md"
    frontmatter, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    authored = authored_skill_md(skill_id)[0]
    block = authored["playbook"]
    assert isinstance(block, dict)
    description = str(frontmatter["description"])
    assert len(description) <= 300, f"{skill_id}: {len(description)} chars"
    # The generated clause follows the authored sentence: "<sentence> Covers <names>."
    assert description.startswith(f"{authored['description']} Covers "), description
    assert description.count(" Covers ") == 1, description
    assert description.endswith(f"Use when {block['use_when']}.")
    assert description.count(" Use when ") == 1
    assert not _TRUNCATION_TAIL.search(description), f"{skill_id} truncates: {description!r}"
    members = _probe_members(pins)
    _assert_covers_clause(skill_id, description, members)
    assert sorted(frontmatter) == ["description", "id", "name"]
    index = body.partition("## Rules\n")[2].partition("## References and examples")[0]
    # A flat index lists one "- [" line per member, a sectioned one one "| [" table row.
    lines = [line for line in index.splitlines() if line.startswith(("- [", "| ["))]
    assert len(lines) == len(members), f"{skill_id} index: {lines}"


def assert_where_section_lists(repo: Path, pins: Iterable[CoreSkillPins]) -> None:
    """``repo``'s AGENTS.md and Claude rules map each skill of ``pins`` to its Where phrase."""
    for relative in ("AGENTS.md", CLAUDE_RULES_PATH):
        text = (repo / relative).read_text(encoding="utf-8")
        assert text.count("## Where guidance lives") == 1, relative
        for skill in pins:
            line = f"- {skill.where}: skill `{skill.skill_id}`"
            assert line in text, f"{relative} lacks {skill.skill_id}"
        assert "Lint feedback names a rule id" in text, relative
