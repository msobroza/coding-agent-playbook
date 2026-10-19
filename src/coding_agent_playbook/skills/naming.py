"""Agent Skills naming rules: the ``name`` and ``description`` limits and their checker.

The Agent Skills standard, read by Claude Code and OpenCode, wants a skill's ``name``
(the playbook emits the skill ``id`` there) to be 1-64 characters of lowercase
alphanumerics separated by single hyphens, and its ``description`` to be 1-1024
characters. :func:`agent_skill_issues` lists the violations of one skill; ``playbook
validate`` reports them up front, because OpenCode drops a skill that breaks them
without a word.

Split out of ``_skill_writer`` for the file-size budget (specs/prS-skills-context.md
§6.4.5), then moved from ``adapters/`` to ``skills/`` (A3), so callers import the
rules from here. A leaf module: ``Skill`` is imported for type checking only, so the
writer can import this module without a cycle.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.skill import Skill

#: Agent Skills ``name`` rule (OpenCode + Claude Code): lowercase alphanumerics
#: separated by single hyphens, 1-64 chars. OpenCode silently skips a skill whose
#: name fails it, which is why ``playbook validate`` checks it up front.
AGENT_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
AGENT_SKILL_NAME_MAX_CHARS = 64
AGENT_SKILL_DESCRIPTION_MAX_CHARS = 1024

#: Fallback id for a skill without an ``id`` key — mirrors the overlay-merge key
#: (``artifacts.identity.artifact_id_of``) and :meth:`Skill.to_prompt`.
_DEFAULT_SKILL_ID = "skill"


def skill_id_of(skill: Skill) -> str:
    """Return the canonical id of ``skill`` (its ``id`` frontmatter key).

    Example: ``skill_id_of(skill)`` -> ``"query-database"``.
    """
    return str(skill.frontmatter.get("id", _DEFAULT_SKILL_ID))


def has_declared_id(skill: Skill) -> bool:
    """Return whether ``skill`` declares an ``id`` key in its frontmatter.

    Id-less skills all merge under the fallback id ``"skill"`` (so all but one
    are silently dropped); ``playbook validate`` uses this to flag each of them.

    Example: ``has_declared_id(skill)`` -> ``True`` for ``id: query-db``.
    """
    return "id" in skill.frontmatter


def agent_skill_issues(skill: Skill) -> list[str]:
    """List the Agent Skills standard violations of ``skill`` (empty = valid).

    Checks that an ``id`` string is declared, the id (emitted as ``name``)
    against :data:`AGENT_SKILL_NAME_PATTERN` and its 1-64 char limit, and that
    ``description`` is 1-1024 chars.

    Example: a skill with ``id: My_Skill`` and no description yields two issues.
    """
    return [*_id_issues(skill), *_description_issues(skill)]


def _id_issues(skill: Skill) -> list[str]:
    if not has_declared_id(skill):
        return [
            f"skill has no 'id'; it is emitted as {_DEFAULT_SKILL_ID!r} and collides "
            "with every other id-less skill (declare 'id:' in its SKILL.md frontmatter)"
        ]
    raw_id = skill.frontmatter["id"]
    if not isinstance(raw_id, str):
        return [f"skill 'id' must be a string, got {type(raw_id).__name__} {raw_id!r}"]
    return _name_issues(raw_id)


def _name_issues(skill_id: str) -> list[str]:
    if len(skill_id) > AGENT_SKILL_NAME_MAX_CHARS:
        return [
            f"skill id {skill_id!r} is {len(skill_id)} chars; the Agent Skills "
            f"name limit is {AGENT_SKILL_NAME_MAX_CHARS}"
        ]
    if AGENT_SKILL_NAME_PATTERN.fullmatch(skill_id):
        return []
    return [
        f"skill id {skill_id!r} is not a valid Agent Skills name (must match "
        f"{AGENT_SKILL_NAME_PATTERN.pattern}); OpenCode silently skips it"
    ]


def _description_issues(skill: Skill) -> list[str]:
    description = str(skill.frontmatter.get("description") or "").strip()
    if not description:
        return ["skill has no 'description'; Agent Skills requires a non-empty description"]
    if len(description) > AGENT_SKILL_DESCRIPTION_MAX_CHARS:
        return [
            f"skill description is {len(description)} chars; the Agent Skills "
            f"limit is {AGENT_SKILL_DESCRIPTION_MAX_CHARS}"
        ]
    return []
