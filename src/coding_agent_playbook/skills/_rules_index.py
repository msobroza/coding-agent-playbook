"""The generated navigation of a skill that declares sections (prU D17, D42, D47, D58).

After the authored body, such a skill's ``SKILL.md`` gets three parts:

1. the fixed "How to use this skill" paragraph (D47, D58);
2. ``## Rules``: its lead, then one ``### <title> [<IMPACT>]`` heading per
   section with at least one active member, in declared order, each with its
   summary, its open-when line and a two-column table ``| Rule | Requires |``;
   members from another layer without ``section:`` close the index under an
   engine-made ``### Other`` (D42);
3. ``## References and examples``: the ``playbook.references`` entries whose
   ``applies_if`` passed, each with its open-when line.

``skills.document`` dispatches here and keeps the flat index of a sectionless
skill; it also takes :func:`section_label` for the Covers clause, which names
sections instead of members (D17, D46.7). Members arrive sorted by
``(section order, priority, id)`` (``skills.membership``); a section keeps the
order it is given.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.member_reference import RULES_DIR, member_reference_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.member_reference import MemberReference
    from coding_agent_playbook.artifacts.skill import ListedReference
    from coding_agent_playbook.skills.sections import SkillSection

RULES_HEADING: Final = "## Rules"
RULES_LEAD: Final = (
    f"Each file under {RULES_DIR}/ is one rule. Open only the ones the current task needs."
)

_HOW_TO_USE_HEADING: Final = "## How to use this skill"
_HOW_TO_USE: Final = (
    "The index below lists only the rules that apply to this repository, most important "
    "first. Find the sections whose open-when line matches the change, then read those "
    "rules in full before editing; usually one to three are enough. Open a reference or "
    "example when a rule names it or its open-when line matches the change."
)
_TABLE_HEAD: Final = ("| Rule | Requires |", "| --- | --- |")
_OTHER_HEADING: Final = "### Other"
_OTHER_SUMMARY: Final = "Rules from other layers that name no section of this skill."
_REFERENCES_HEADING: Final = "## References and examples"


def sectioned_navigation(
    members: Sequence[MemberReference],
    sections: Sequence[SkillSection],
    references: Sequence[ListedReference],
) -> str:
    """The three generated parts of a sectioned skill, ``\\n``-terminated.

    Example: ``sectioned_navigation(members, sections, ()).startswith("## How to use")``
    -> ``True``.
    """
    parts = [
        f"{_HOW_TO_USE_HEADING}\n\n{_HOW_TO_USE}\n",
        sectioned_rules_index(members, sections),
        references_section(references),
    ]
    return "\n".join(part for part in parts if part)


def sectioned_rules_index(
    members: Sequence[MemberReference], sections: Sequence[SkillSection]
) -> str:
    """``## Rules``, its lead, then one block per section that has an active member.

    A member whose ``section`` is ``None`` or names no declared section is
    listed under ``### Other``, after the declared sections. ``""`` without members.

    Example: ``sectioned_rules_index(members, sections).splitlines()[4]`` ->
    ``"### Mocking [CRITICAL]"``.
    """
    if not members:
        return ""
    declared = {section.id for section in sections}
    blocks = [
        _section_block(section, [m for m in members if m.section == section.id])
        for section in sections
    ]
    others = [member for member in members if member.section not in declared]
    blocks.append(_other_block(others))
    body = "\n".join(block for block in blocks if block)
    return f"{RULES_HEADING}\n\n{RULES_LEAD}\n\n{body}"


def references_section(references: Sequence[ListedReference]) -> str:
    """``## References and examples``, one line per listed entry; ``""`` without entries.

    Example: ``references_section([ListedReference("references/a.md", "X.")])`` ->
    ``"## References and examples\\n\\n- [references/a.md](references/a.md) — Open when: X.\\n"``.
    """
    if not references:
        return ""
    lines = [
        f"- [{ref.path}]({ref.path}) — Open when: {_one_line(ref.open_when)}" for ref in references
    ]
    return "\n".join([_REFERENCES_HEADING, "", *lines, ""])


def active_sections(
    members: Sequence[MemberReference], sections: Sequence[SkillSection]
) -> list[SkillSection]:
    """The declared sections with at least one of ``members``, in declared order.

    Example: ``[s.id for s in active_sections(members, sections)]`` -> ``["mocking"]``.
    """
    used = {member.section for member in members}
    return [section for section in sections if section.id in used]


def section_label(title: str) -> str:
    """A section title as the Covers clause names it (D46.7).

    Each word is lowercased unless a letter after its first is a capital, so
    ``FastAPI``, ``HTTP``, ``CQRS`` and ``I/O`` stay as written.

    Example: ``section_label("Test Structure")`` -> ``"test structure"``;
    ``section_label("FastAPI wiring")`` -> ``"FastAPI wiring"``.
    """
    return " ".join(_word_label(word) for word in title.split())


def _word_label(word: str) -> str:
    """``word`` lowercased, unless it holds a capital after its first character."""
    return word if any(char.isupper() for char in word[1:]) else word.lower()


def _section_block(section: SkillSection, members: Sequence[MemberReference]) -> str:
    """One section's heading, summary, open-when line and table; ``""`` without members."""
    if not members:
        return ""
    return "\n".join(
        [
            f"### {section.title} [{section.impact}]",
            "",
            section.summary,
            "",
            f"Open when: {section.open_when}",
            "",
            *_table(members),
        ]
    )


def _other_block(members: Sequence[MemberReference]) -> str:
    """D42's engine-made section for members that name no declared section."""
    if not members:
        return ""
    return "\n".join([_OTHER_HEADING, "", _OTHER_SUMMARY, "", *_table(members)])


def _table(members: Sequence[MemberReference]) -> list[str]:
    """The two-column table of ``members``, ``""``-terminated so blocks stack with a blank line."""
    rows = [
        f"| [{m.rule_id}]({member_reference_path(m.rule_id)}) | "
        f"{_cell(m.name)}: {_cell(m.description)} |"
        for m in members
    ]
    return [*_TABLE_HEAD, *rows, ""]


def _cell(text: str) -> str:
    """``text`` on one line with its pipes escaped, safe inside a table cell."""
    return _one_line(text).replace("|", "\\|")


def _one_line(text: str) -> str:
    """``text`` with every whitespace run, newlines included, collapsed to one space."""
    return " ".join(text.split())
