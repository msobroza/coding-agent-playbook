"""``playbook validate`` over skill sections (prU D17, D32, D42, D46.8, D47; ADR 0005).

A skill's ``playbook.sections`` list (shape in ``skills.sections``) groups its
member rules; each member names its entry in ``section:`` and takes a priority
inside that section's impact band. The checks, each finding naming the file or
the skill label, the value and the allowed values or band:

- S1, per skill: the list's shape (a list of mappings with exactly ``id``,
  ``title``, ``impact``, ``summary`` and a one-line ``open_when``; kebab-case
  ids, unique; titles of at most 40 chars; a known impact). ``sections: []``
  declares no sections.
- S2, per skill: sections run from CRITICAL to LOW.
- S3, per member: its ``section:`` is declared by its skill.
- S4, per member: a member of a sectioned skill sets ``section:`` when it comes
  from the skill's own layer or from the repository (``<repo-local>``, which the
  repo owner can edit), including a rule joining by ``skill:``. A member from
  another overlay or bundled layer without one only warns (D42): it is listed
  under the engine's "Other" section, after the declared ones. When a higher
  layer replaces a skill and declares sections, the replaced layer's members are
  such members: their authors cannot see the new sections.
- S5, per rule: ``section:`` on an always rule, or on a member of a skill that
  declares no sections.
- S6, per member: its priority lies in its section's band. Bands apply only to
  sectioned skills (D46.8).
- S7, per member of a sectioned skill: its first heading carries no authored
  ``[IMPACT]`` tag; the engine renders the tag from the section (D32). Members of
  a skill without sections are left as they are today.

Member checks wait until S1 accepts the list, so a broken list reports once.
A declared section without members is no finding: it would print on every sync
while content lanes fill a skill. ``playbook.references`` (D47) is checked by
``validation._skill_references``, wired in here.
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.impact import Impact
from coding_agent_playbook.catalog.layers import REPO_LOCAL_SOURCE
from coding_agent_playbook.skills.membership import is_rule_skill, member_rules_of
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.skills.sections import (
    SECTIONS_FIELD,
    SkillSection,
    declared_sections_value,
    section_list_problems,
    skill_sections,
)
from coding_agent_playbook.validation._skill_references import (
    PredicateCheck,
    skill_reference_problems,
)
from coding_agent_playbook.validation.findings import (
    ValidationError,
    ValidationFindings,
    skill_label,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

_FENCE: Final = re.compile(r"^\s*(```|~~~)")
_HEADING: Final = re.compile(r"^#{1,6}\s")
_IMPACT_TAG: Final = re.compile(r"\[(" + "|".join(Impact) + r")\]\s*$")


def check_skill_sections(
    resolved_rules: Sequence[Rule], skills: Sequence[Skill], *, check_predicate: PredicateCheck
) -> ValidationFindings:
    """S1-S7, the D42 warning and the ``playbook.references`` checks over the merged sets.

    ``check_predicate`` evaluates one ``applies_if`` mapping and raises
    ``ValueError`` when it is malformed (validate binds the detector facts).

    Example::

        findings = check_skill_sections(
            ctx.rules_resolved, ctx.skills_resolved, check_predicate=lambda p: None
        )
    """
    errors = [_rule_error(rule, m) for rule in resolved_rules for m in _always_rule_problems(rule)]
    warnings: list[ValidationError] = []
    for skill in filter(is_rule_skill, skills):
        findings = _skill_findings(skill, resolved_rules, check_predicate)
        errors.extend(findings.errors)
        warnings.extend(findings.warnings)
    return ValidationFindings(errors, warnings)


def _skill_findings(
    skill: Skill, resolved_rules: Sequence[Rule], check_predicate: PredicateCheck
) -> ValidationFindings:
    """Every check of one skill with a ``playbook:`` block, and of its members."""
    members = member_rules_of(skill_id_of(skill), resolved_rules)
    label = skill_label(skill)
    skill_problems = [*_list_problems(skill), *skill_reference_problems(skill, check_predicate)]
    member_findings = _member_findings(skill, members)
    return ValidationFindings(
        [*(ValidationError(label, m) for m in skill_problems), *member_findings.errors],
        member_findings.warnings,
    )


def _rule_error(rule: Rule, message: str) -> ValidationError:
    """A finding located at the rule's file (its id without one)."""
    return ValidationError(path=str(rule.source_path or rule.frontmatter.id), message=message)


def _always_rule_problems(rule: Rule) -> list[str]:
    """S5 for an always rule that sets ``section:``."""
    section = rule.frontmatter.section
    if rule.frontmatter.scope != "always" or section is None:
        return []
    return [
        f"'section: {section}' is not allowed on an always rule (sections group a skill's "
        "member rules); remove 'section'"
    ]


def _list_problems(skill: Skill) -> list[str]:
    """S1 on the ``sections`` value, then S2 once the list is sound."""
    value = declared_sections_value(skill)
    if value is None:
        return []
    return section_list_problems(value) or list(_order_problems(skill_sections(skill)))


def _order_problems(sections: Sequence[SkillSection]) -> Iterator[str]:
    """S2: one problem per section whose impact ranks above the one before it."""
    for before, section in pairwise(sections):
        if section.impact.rank < before.impact.rank:
            yield (
                f"{SECTIONS_FIELD} must run from CRITICAL to LOW: section {section.id!r} "
                f"({section.impact}) comes after {before.id!r} ({before.impact})"
            )


def _impact_tag_problems(rule: Rule) -> list[str]:
    """S7: the member's first heading (outside code fences) ends with an impact tag."""
    heading = _first_heading(rule.template_body)
    match = None if heading is None else _IMPACT_TAG.search(heading)
    if heading is None or match is None:
        return []
    return [
        f"the first heading {heading!r} carries an impact tag; remove '[{match.group(1)}]' "
        "(the engine renders it from the rule's section)"
    ]


def _first_heading(body: str) -> str | None:
    """The first ATX heading line of ``body`` outside fenced code, stripped; ``None`` if none."""
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and _HEADING.match(line):
            return line.strip()
    return None


def _member_findings(skill: Skill, members: Sequence[Rule]) -> ValidationFindings:
    """S3, S4, S6, S7 and D42's warning per member, or S5 alone for a skill without sections."""
    if declared_sections_value(skill) is None:
        sectioned = [rule for rule in members if rule.frontmatter.section is not None]
        return ValidationFindings(
            [_rule_error(r, _sectionless_problem(skill, r)) for r in sectioned]
        )
    sections = skill_sections(skill)
    if not sections:  # S1 already reported the list
        return ValidationFindings()
    errors = [
        _rule_error(rule, problem)
        for rule in members
        for problem in (_member_problem(skill, sections, rule), *_impact_tag_problems(rule))
        if problem is not None
    ]
    warnings = [
        _rule_error(rule, _other_section_warning(skill, sections))
        for rule in members
        if _joins_other_section(skill, rule)
    ]
    return ValidationFindings(errors, warnings)


def _sectionless_problem(skill: Skill, rule: Rule) -> str:
    """S5 for a member of a skill that declares no sections."""
    return (
        f"'section: {rule.frontmatter.section}' is not allowed: skill {skill_id_of(skill)!r} "
        f"declares no {SECTIONS_FIELD}; remove 'section', or declare the section in that skill"
    )


def _joins_other_section(skill: Skill, rule: Rule) -> bool:
    """D42: a member without ``section:`` from a layer its author cannot align lands in "Other".

    The repository's own rules are never such members: the repo owner edits them
    and sees the skill's sections, so S4 holds for them (the ticket's acceptance).
    """
    return (
        rule.frontmatter.section is None
        and rule.source_package != skill.source_package
        and rule.source_package != REPO_LOCAL_SOURCE
    )


def _other_section_warning(skill: Skill, sections: Sequence[SkillSection]) -> str:
    """D42's warning text, naming the skill and its declared sections."""
    return (
        f"joins skill {skill_id_of(skill)!r} ({skill.source_package}) from another layer "
        "without 'section:'; it is listed under 'Other', after the declared sections: "
        f"{_section_ids(sections)}"
    )


def _member_problem(skill: Skill, sections: Sequence[SkillSection], rule: Rule) -> str | None:
    """S4, S3 or S6 for one member of a sectioned skill; ``None`` when it is sound."""
    section_id = rule.frontmatter.section
    if _joins_other_section(skill, rule):
        return None
    if section_id is None:
        return (
            f"skill {skill_id_of(skill)!r} declares sections, so its member rule needs "
            f"'section:'; declared sections: {_section_ids(sections)}"
        )
    section = next((s for s in sections if s.id == section_id), None)
    if section is None:
        return (
            f"section {section_id!r} is not declared by skill {skill_id_of(skill)!r}; "
            f"declared sections: {_section_ids(sections)}"
        )
    return _band_problem(rule, section)


def _section_ids(sections: Sequence[SkillSection]) -> str:
    """The declared ids in order, comma-separated, as S3, S4 and D42 list them."""
    return ", ".join(section.id for section in sections)


def _band_problem(rule: Rule, section: SkillSection) -> str | None:
    """S6: the member's priority lies in its section's impact band."""
    priority: object = rule.frontmatter.priority
    band = section.impact.band
    if isinstance(priority, int) and not isinstance(priority, bool) and priority in band:
        return None
    return (
        f"priority {priority!r} is outside the band of section {section.id!r} "
        f"({section.impact}): expected {band[0]}-{band[-1]}"
    )
