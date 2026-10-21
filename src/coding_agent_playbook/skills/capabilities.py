"""Framework capabilities: the standard roles a framework's skills are tagged with (D74, D77).

A framework skill lists its roles in the engine-owned frontmatter key
``capabilities: [clarify]``; the key is removed when the skill is written out
(``skills.document.emitted_frontmatter``), like the ``playbook:`` block. Only the
enabled framework's tags are read: :func:`framework_role_map` derives its
role-to-skill map, which templates reach through ``framework_skill(role)`` and
``playbook check`` prints (:func:`format_role_map`). ``playbook validate``
accepts only :data:`CAPABILITY_ROLES` and at most one skill per role
(:func:`capability_problems`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard

from coding_agent_playbook.skills.naming import skill_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.artifacts.skill import Skill

#: The engine-owned frontmatter key holding a framework skill's roles (D77).
CAPABILITIES_KEY: Final = "capabilities"

#: The standard roles of D74, in the order ``playbook check`` prints them.
CAPABILITY_ROLES: Final = (
    "clarify",
    "clarify_with_docs",
    "spec",
    "plan",
    "tdd",
    "debug",
    "review",
    "verify",
)


def framework_role_map(skills: Sequence[Skill], package: str | None) -> dict[str, str]:
    """``{role: skill id}`` from the tags of ``package``'s skills, in role order.

    ``package`` is the enabled framework's layer (``None``: no framework, so
    ``{}``). Unknown roles are skipped and the first skill tagged with a role
    keeps it; validate reports both (:func:`capability_problems`).

    Example::

        framework_role_map(ctx.skills_resolved, "coding_agent_playbook.plugins.superpowers")
        # {'clarify': 'brainstorming', 'plan': 'writing-plans', ...}
    """
    found: dict[str, str] = {}
    for skill in _framework_skills(skills, package):
        for role in _declared_roles(skill):
            found.setdefault(role, skill_id_of(skill))
    return {role: found[role] for role in CAPABILITY_ROLES if role in found}


def capability_problems(skills: Sequence[Skill], package: str | None) -> list[tuple[str, str]]:
    """``(skill id, problem)`` for each bad tag of ``package``'s skills; ``[]`` when sound.

    A tag must be a list of D74 role names, and one framework tags each role on
    one skill only. Skills of other layers are never read (D77).

    Example::

        capability_problems(skills, "acme.framework")
        # [('a', "capabilities has unknown role 'deploy'; known roles: clarify, ...")]
    """
    problems: list[tuple[str, str]] = []
    owners: dict[str, str] = {}
    for skill in _framework_skills(skills, package):
        skill_id = skill_id_of(skill)
        value = skill.frontmatter[CAPABILITIES_KEY]
        if not _is_name_list(value):
            problems.append(
                (skill_id, f"{CAPABILITIES_KEY} must be a list of role names, got {value!r}")
            )
            continue
        for role in value:
            problems.extend(_role_problem(skill_id, role, owners))
    return problems


def format_role_map(framework_name: str, roles: Mapping[str, str]) -> str:
    """The ``playbook check`` line: ``framework <name>: <role> -> <skill>, ...``.

    Example::

        >>> format_role_map("mattpocock", {"debug": "diagnosing-bugs"})
        'framework mattpocock: debug -> diagnosing-bugs'
    """
    pairs = ", ".join(f"{role} -> {skill}" for role, skill in roles.items())
    return f"framework {framework_name}: {pairs or '(no capabilities declared)'}"


def _role_problem(skill_id: str, role: str, owners: dict[str, str]) -> list[tuple[str, str]]:
    """The problem with ``skill_id`` tagging ``role``, recording the first owner of each role."""
    if role not in CAPABILITY_ROLES:
        known = ", ".join(CAPABILITY_ROLES)
        return [(skill_id, f"{CAPABILITIES_KEY} has unknown role {role!r}; known roles: {known}")]
    owner = owners.setdefault(role, skill_id)
    if owner == skill_id:
        return []
    return [
        (
            skill_id,
            f"{CAPABILITIES_KEY} role {role!r} is already declared by skill {owner!r}; "
            "one skill per role",
        )
    ]


def _framework_skills(skills: Sequence[Skill], package: str | None) -> list[Skill]:
    """``package``'s skills that carry the tag key, in order."""
    if package is None:
        return []
    return [s for s in skills if s.source_package == package and CAPABILITIES_KEY in s.frontmatter]


def _declared_roles(skill: Skill) -> list[str]:
    """The known roles ``skill`` tags; a malformed tag reads as none."""
    value = skill.frontmatter.get(CAPABILITIES_KEY)
    if not _is_name_list(value):
        return []
    return [role for role in value if role in CAPABILITY_ROLES]


def _is_name_list(value: object) -> TypeGuard[list[str]]:
    """True for a list whose every item is a string."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
