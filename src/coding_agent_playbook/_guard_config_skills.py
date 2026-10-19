"""skill-nudge's glob table, derived at sync from the member rules (specs/prS-skills-context.md 8.5.2).

A scoped rule names the skill that delivers it (``skill:``, ADR 0001), and its
``globs`` say which files it covers. Grouped by skill, those globs tell the
skill-nudge builtin which skill to name when a session first edits a file, so
the runtime never imports the catalog. The table travels as the hook's derived
config (``gc:skill-nudge.skills``), merged last by ``with_derived_config``, and
no ``CONFIG_SCHEMA`` declares ``skills``: a layer cannot set or widen it.
Machine-independent: the rendered rules only (§D.8.3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypedDict

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.types import Rule

__all__ = ["SKILL_NUDGE_HOOK_ID", "SkillGlobRow", "skill_glob_rows"]

SKILL_NUDGE_HOOK_ID: Final = "skill-nudge"


class SkillGlobRow(TypedDict):
    """One row of ``gc:skill-nudge.skills``: a written skill and its member globs, as JSON.

    Example: ``{"id": "python-testing", "globs": ["tests/**/*.py"]}``.
    """

    id: str
    globs: list[str]


def skill_glob_rows(rules: Iterable[Rule]) -> list[SkillGlobRow]:
    """``[{"id": <skill>, "globs": [...]}]`` from the scoped member rules, sorted by skill id.

    ``rules`` are the rules this sync renders, already ``applies_if``-filtered,
    so a skill appears only when it is written. A rule without ``skill`` or
    ``globs`` adds nothing; a skill's globs keep first-seen order, each once.

    Example::

        >>> skill_glob_rows([pytest_rule])  # doctest: +SKIP
        [{'id': 'python-testing', 'globs': ['tests/**/*.py']}]
    """
    globs_by_skill: dict[str, dict[str, None]] = {}
    for rule in rules:
        skill_id = rule.frontmatter.skill
        if skill_id and rule.frontmatter.globs:
            globs_by_skill.setdefault(skill_id, {}).update(dict.fromkeys(rule.frontmatter.globs))
    return [
        SkillGlobRow(id=skill_id, globs=list(globs))
        for skill_id, globs in sorted(globs_by_skill.items())
    ]
