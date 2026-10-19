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
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.skills.document import PLAYBOOK_BLOCK_KEY, render_member_reference
from coding_agent_playbook.skills.naming import skill_id_of

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

#: The built-in adapters that write skill references, named by the undelivered warning.
_SKILL_REFERENCE_ADAPTERS: Final = "claude_code, opencode or shared_skills"


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
    skills: Sequence[Skill], merged_rules: Sequence[Rule], active_rules: Sequence[Rule]
) -> list[Skill]:
    """The skills to write, each with its active member rules attached.

    A skill without a ``playbook`` block passes through unchanged (V14 keeps
    rules from naming it). A skill with the block is dropped when none of its
    members survived ``applies_if``; otherwise it gets one
    :class:`MemberReference` per active member, built from the Jinja-rendered
    rule. Membership comes from ``merged_rules`` (every layer merged, before
    ``applies_if``); ``active_rules`` (filtered, bodies rendered) decides which
    members are on and supplies their text. Never mutates its inputs. Example::

        skills = compose_skills(ctx.skills_resolved, ctx.rules_resolved, rendered_rules)
    """
    active_by_id = {rule.frontmatter.id: rule for rule in active_rules}
    composed = (_composed_skill(skill, merged_rules, active_by_id) for skill in skills)
    return [skill for skill in composed if skill is not None]


def member_reference(rule: Rule) -> MemberReference:
    """``rule`` (body already rendered) as the reference its skill writes.

    Example: ``member_reference(rendered_typing_rule).filename`` -> ``"python-typing.md"``.
    """
    fm = rule.frontmatter
    return MemberReference(
        rule_id=fm.id,
        name=fm.name,
        description=fm.description,
        priority=fm.priority,
        globs=tuple(fm.globs),
        text=render_member_reference(fm.id, fm.globs, rule.body),
        source_package=rule.source_package,
    )


def undelivered_member_warning(adapters: Iterable[Adapter], skills: Sequence[Skill]) -> str | None:
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
    skill: Skill, merged_rules: Sequence[Rule], active_by_id: Mapping[str, Rule]
) -> Skill | None:
    """``skill`` as written: unchanged when plain, None without an active member."""
    if not is_rule_skill(skill):
        return skill
    member_ids = [rule.frontmatter.id for rule in member_rules_of(skill_id_of(skill), merged_rules)]
    active = [active_by_id[rule_id] for rule_id in member_ids if rule_id in active_by_id]
    if not active:
        return None
    return dataclasses.replace(skill, member_references=tuple(map(member_reference, active)))


def _enabled_phrase(adapters: Sequence[Adapter]) -> str:
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
