"""Skill membership and gating: which skills a sync writes, with which member rules.

A scoped rule that names a skill in ``skill:`` is a member rule of that skill
(ADR 0001): the engine delivers it as one of the skill's references instead of
writing it into always-loaded context. A skill is gated on member rules exactly
when it declares the catalog-only ``playbook:`` block (E6): such a skill is
written only when at least one member passed ``applies_if``. A skill without
the block (a bundled plugin skill, a plain repo-local skill) never takes members
and passes through unchanged. See specs/prS-skills-context.md section 6.4.3.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Final, Protocol, TypeGuard

from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.artifacts.skill import ListedReference
from coding_agent_playbook.skills._rules_index import one_line
from coding_agent_playbook.skills.document import render_member_reference
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.skills.playbook_block import PLAYBOOK_BLOCK_KEY, playbook_block
from coding_agent_playbook.skills.sections import REFERENCES_KEY, section_rank, skill_sections

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.skills.sections import SkillSection

#: Whether one ``playbook.references`` entry's ``applies_if`` mapping holds (D47, D58).
#: Sync binds the detector facts (``detector.predicate.evaluate_predicate``).
type ReferenceGate = Callable[[dict[str, Any]], bool]

#: The built-in adapters that write skill references, named by the undelivered warning.
_SKILL_REFERENCE_ADAPTERS: Final = "claude_code, opencode or shared_skills"


def _every_reference_applies(_predicate: dict[str, Any]) -> bool:
    """The default gate: with no facts at hand, every entry is listed."""
    return True


class MemberRuleDeliverer(Protocol):
    """The two ``Adapter`` members :func:`undelivered_member_warning` reads.

    A local protocol, typed as ``adapters.base.Adapter`` declares them, so the
    skills layer never imports the adapters layer above it (engine-layers, SK-1).
    Every adapter satisfies it structurally. Example::

        undelivered_member_warning([AgentsMdAdapter()], skills)
    """

    name: str
    delivers_member_rules: ClassVar[bool]


def is_skill_member(rule: Rule) -> bool:
    """Whether ``rule`` is delivered through a skill (its frontmatter names one).

    Example: ``is_skill_member(typing_rule)`` -> ``True`` for ``skill: python-coding``.
    """
    return rule.frontmatter.skill is not None


def member_rules_of(skill_id: str, rules: Sequence[Rule]) -> list[Rule]:
    """The rules whose ``skill`` is ``skill_id``, sorted by ``(priority, id)``.

    Example: ``[r.frontmatter.id for r in member_rules_of("python-testing", rules)]``
    -> ``["pytest"]``.
    """
    members = [rule for rule in rules if rule.frontmatter.skill == skill_id]
    return sorted(members, key=lambda rule: (rule.frontmatter.priority, rule.frontmatter.id))


def is_rule_skill(skill: Skill) -> bool:
    """Whether ``skill`` is gated on member rules: it declares a ``playbook`` block (E6).

    Example: ``is_rule_skill(python_coding)`` -> ``True``; ``False`` for a plugin skill.
    """
    return PLAYBOOK_BLOCK_KEY in skill.frontmatter


def compose_skills(
    skills: Sequence[Skill],
    merged_rules: Sequence[Rule],
    active_rules: Sequence[Rule],
    *,
    reference_applies: ReferenceGate = _every_reference_applies,
) -> list[Skill]:
    """The skills to write, each with its active member rules attached.

    A skill without a ``playbook`` block passes through unchanged (V14 keeps
    rules from naming it). A skill with the block is dropped when none of its
    members survived ``applies_if``; otherwise it gets one
    :class:`MemberReference` per active member, built from the Jinja-rendered
    rule. Membership comes from ``merged_rules`` (every layer merged, before
    ``applies_if``); ``active_rules`` (filtered, bodies rendered) decides which
    members are on and supplies their text. Members are ordered by
    ``(priority, id)``; in a skill that declares sections, by section first,
    members in no declared section last (D17, D42). The skill's
    ``listed_references`` are its ``playbook.references`` entries whose
    ``applies_if`` passes ``reference_applies`` (D47). Never mutates its inputs.
    Example::

        skills = compose_skills(ctx.skills_resolved, ctx.rules_resolved, rendered_rules)
    """
    active_by_id = {rule.frontmatter.id: rule for rule in active_rules}
    composed = (
        _composed_skill(skill, merged_rules, active_by_id, reference_applies) for skill in skills
    )
    return [skill for skill in composed if skill is not None]


def active_skill_ids(
    skills: Sequence[Skill], merged_rules: Sequence[Rule], active_rules: Sequence[Rule]
) -> frozenset[str]:
    """The ids of the skills :func:`compose_skills` keeps, without rendering anything.

    What a template's ``skill_active(name)`` reads (D74): a plain skill always
    renders, a skill with a ``playbook`` block only when one of its members is
    in ``active_rules`` (the same rule as :func:`compose_skills`, ``_is_kept``).
    One known gap: ``playbook-guardrails`` counts as active when authored, but
    sync splits it off and writes it only when an on hook has advisory text
    (``hooks.guardrails_skill``), which is resolved after the templates render;
    templates should not gate on it. Example::

        active_skill_ids(ctx.skills_resolved, ctx.rules_resolved, applicable_rules)
    """
    active_by_id = {rule.frontmatter.id: rule for rule in active_rules}
    return frozenset(
        skill_id_of(skill) for skill in skills if _is_kept(skill, merged_rules, active_by_id)
    )


def member_reference(rule: Rule, sections: Sequence[SkillSection] = ()) -> MemberReference:
    """``rule`` (body already rendered) as the reference its skill writes.

    ``sections`` are its skill's declared sections: a member whose ``section:``
    names one carries that section's id and impact; any other member carries
    neither (a sectionless skill, or D42's "Other").

    Example: for the rendered ``python-typing`` rule, ``member_reference(rule).filename``
    -> ``"python-typing.md"``.
    """
    fm = rule.frontmatter
    section = next((s for s in sections if s.id == fm.section), None)
    return MemberReference(
        rule_id=fm.id,
        name=fm.name,
        description=fm.description,
        priority=fm.priority,
        globs=tuple(fm.globs),
        text=render_member_reference(fm.id, fm.globs, rule.body),
        source_package=rule.source_package,
        section=None if section is None else section.id,
        impact=None if section is None else section.impact,
    )


def undelivered_member_warning(
    adapters: Iterable[MemberRuleDeliverer], skills: Sequence[Skill]
) -> str | None:
    """A ``warning:`` line when member rules are active but no enabled adapter delivers them.

    ``None`` when some adapter has ``delivers_member_rules`` (section 6.4.10) or
    no skill carries members. Example::

        warning = undelivered_member_warning(ctx.adapters.values(), rendered.skills)
    """
    enabled = list(adapters)
    if any(adapter.delivers_member_rules for adapter in enabled):
        return None
    composed = sorted(skill_id_of(skill) for skill in skills if skill.member_references)
    if not composed:
        return None
    return (
        f"warning: no enabled adapter delivers scoped rules ({_enabled_phrase(enabled)}); "
        f"{_unreached_phrase(composed)} no assistant: add {_SKILL_REFERENCE_ADAPTERS} "
        "to adapters_enabled"
    )


def _composed_skill(
    skill: Skill,
    merged_rules: Sequence[Rule],
    active_by_id: Mapping[str, Rule],
    reference_applies: ReferenceGate,
) -> Skill | None:
    """``skill`` as written: unchanged when plain, None without an active member."""
    if not _is_kept(skill, merged_rules, active_by_id):
        return None
    if not is_rule_skill(skill):
        return skill
    sections = skill_sections(skill)
    rank = section_rank(sections)
    active = _active_members(skill, merged_rules, active_by_id)
    members = sorted(
        (member_reference(rule, sections) for rule in active),
        key=lambda member: rank(member.section),
    )  # stable: (priority, id) order holds within a section
    return dataclasses.replace(
        skill,
        member_references=tuple(members),
        listed_references=_listed_references(skill, reference_applies),
    )


def _listed_references(
    skill: Skill, reference_applies: ReferenceGate
) -> tuple[ListedReference, ...]:
    """The ``playbook.references`` entries whose ``applies_if`` passes, in declared order (D47).

    An entry validate would reject (not a mapping, no string ``path`` or
    ``open_when``, an ``applies_if`` that is no mapping) is skipped.
    """
    entries = playbook_block(skill).get(REFERENCES_KEY)
    if not isinstance(entries, list):
        return ()
    return tuple(
        ListedReference(entry["path"], one_line(entry["open_when"]))
        for entry in entries
        if _is_listable_entry(entry)
        and ("applies_if" not in entry or reference_applies(dict(entry["applies_if"])))
    )


def _is_listable_entry(entry: object) -> TypeGuard[Mapping[str, Any]]:
    """A mapping with string ``path`` and ``open_when`` and a mapping (or no) ``applies_if``."""
    return (
        isinstance(entry, Mapping)
        and isinstance(entry.get("path"), str)
        and isinstance(entry.get("open_when"), str)
        and isinstance(entry.get("applies_if", {}), Mapping)
    )


def _is_kept(skill: Skill, merged_rules: Sequence[Rule], active_by_id: Mapping[str, Rule]) -> bool:
    """The one keep/drop rule of :func:`compose_skills` and :func:`active_skill_ids`.

    A plain skill is always kept; a gated one (``playbook`` block) only with an
    active member.
    """
    return not is_rule_skill(skill) or bool(_active_members(skill, merged_rules, active_by_id))


def _active_members(
    skill: Skill, merged_rules: Sequence[Rule], active_by_id: Mapping[str, Rule]
) -> list[Rule]:
    """``skill``'s member rules that are active, as ``active_by_id`` holds them, in order."""
    member_ids = [rule.frontmatter.id for rule in member_rules_of(skill_id_of(skill), merged_rules)]
    return [active_by_id[rule_id] for rule_id in member_ids if rule_id in active_by_id]


def _enabled_phrase(adapters: Sequence[MemberRuleDeliverer]) -> str:
    """``only agents_md is on`` / ``only a, b are on`` / ``no adapter is on``."""
    names = sorted(adapter.name for adapter in adapters)
    if not names:
        return "no adapter is on"
    verb = "is" if len(names) == 1 else "are"
    return f"only {', '.join(names)} {verb} on"


def _unreached_phrase(skill_ids: Sequence[str]) -> str:
    """``skill a reaches`` / ``skills a, b reach``."""
    listed = ", ".join(skill_ids)
    return f"skill {listed} reaches" if len(skill_ids) == 1 else f"skills {listed} reach"
