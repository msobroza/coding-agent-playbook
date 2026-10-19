"""The ``playbook-guardrails`` skill: the full guardrail text of the on hooks (D6).

Core ships an authored ``catalog/core/skills/playbook-guardrails/SKILL.md`` with
no member rules and no ``playbook:`` block. Sync takes it out of the skills
every adapter receives (:func:`split_guardrails_skill`), composes it with one
section per on hook that has guardrail text (:func:`compose_guardrails_skill`),
and hands the result only to the adapters whose ``writes_guardrails_skill``
says so (specs/prS-skills-context.md 8.4.3). Stdlib-only, like the rest of
``hook_policy``.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.hook_policy.resolved import ResolvedHook

__all__ = [
    "GUARDRAILS_SKILL_ID",
    "compose_guardrails_skill",
    "has_guardrail_text",
    "split_guardrails_skill",
]

#: The id (and output directory name) of the guardrails skill. An overlay or
#: repo-local skill with this id replaces the authored text and still gets the
#: generated sections.
GUARDRAILS_SKILL_ID: Final = "playbook-guardrails"


def split_guardrails_skill(skills: Sequence[Skill]) -> tuple[list[Skill], Skill | None]:
    """``skills`` without the authored guardrails skill, and that skill (``None`` if absent).

    Example::

        regular, authored = split_guardrails_skill(compose_skills(skills, merged, active))
    """
    regular = [skill for skill in skills if not _is_guardrails_skill(skill)]
    authored = next((skill for skill in skills if _is_guardrails_skill(skill)), None)
    return regular, authored


def _is_guardrails_skill(skill: Skill) -> bool:
    """Whether ``skill`` declares the guardrails skill's id (a merged set holds one per id)."""
    return skill.frontmatter.get("id") == GUARDRAILS_SKILL_ID


def has_guardrail_text(hooks: Iterable[ResolvedHook]) -> bool:
    """Whether any of ``hooks`` has guardrail text (an advisory), so the skill gets a section.

    A hook has none when its body is blank or ``[hooks] advisory = false``.

    Example: ``has_guardrail_text([])`` -> ``False``.
    """
    return any(hook.advisory is not None for hook in hooks)


def compose_guardrails_skill(authored: Skill | None, hooks: Sequence[ResolvedHook]) -> Skill | None:
    """The authored skill with one section per on hook that has an advisory, or ``None``.

    Sections are sorted by hook id; each is ``## <name> (`<id>`)`` over the
    hook's advisory text (rendered body plus its enforcement line, the text of
    its ``AGENTS.md`` guardrail block). ``None`` when ``authored`` is ``None`` or
    no hook has an advisory (hooks off, no hook with a body, or ``[hooks]
    advisory = false``): the skill is then not written at all. Never mutates
    ``authored``.

    Example::

        compose_guardrails_skill(authored, rendered.hooks.resolved)
    """
    texts = sorted(
        (hook.id, hook.name, hook.advisory.body) for hook in hooks if hook.advisory is not None
    )
    if authored is None or not texts:
        return None
    sections = "\n".join(_section(hook_id, name, text) for hook_id, name, text in texts)
    intro = authored.body.rstrip()
    body = f"{intro}\n\n{sections}" if intro else sections
    return dataclasses.replace(authored, body=body)


def _section(hook_id: str, name: str, text: str) -> str:
    """``## <name> (`<id>`)``, a blank line, then ``text`` ending in exactly one newline."""
    prose = text.strip("\n")
    return f"## {name} (`{hook_id}`)\n\n{prose}\n"
