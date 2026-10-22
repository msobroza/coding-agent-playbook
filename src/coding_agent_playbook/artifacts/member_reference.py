"""A member rule as its skill delivers it: one ``rules/<rule-id>.md`` file.

A scoped rule that names a skill in ``skill:`` is a member rule of that skill
(ADR 0001). At sync, ``skills.membership.compose_skills`` renders each active
member into a :class:`MemberReference` and attaches them to
``Skill.member_references``; the skill writer then writes ``text`` under every
skill root, so the copies are byte-identical.

A stdlib-only leaf: ``artifacts.skill`` imports it at run time for
``Skill.from_dict``, so it cannot import ``artifacts.skill`` back
(specs/prS-skills-context.md section 6.4.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The directory inside a skill that holds its member rules, as in the source
#: (prU D5, ADR 0005); ``references/`` stays free for hand-written documents.
#: Generated wording that names the directory (skills.document, validation V6)
#: is built from it too, so a rename touches this one line.
RULES_DIR: Final = "rules"

#: The directory of skills under a playbook layer and under the harness tree alike.
SKILLS_DIR: Final = "skills"


def member_reference_path(rule_id: str) -> str:
    """Where a member rule lives inside its skill directory (E16).

    The one spelling the writer, the lockfile split and prompt pointer lines share.

    Example: ``member_reference_path("pytest")`` -> ``"rules/pytest.md"``.
    """
    return f"{RULES_DIR}/{rule_id}.md"


def skill_member_path(skill_id: str, rule_id: str, *, suffix: str = ".md") -> str:
    """A member rule's path relative to the root that holds ``skills/`` (prU D5, D22).

    The one spelling of ``skills/<skill>/rules/<id><suffix>`` that the
    agent_harness emitter, its manifest and ``import-harness`` share;
    :func:`skill_member_location` parses it back.

    Example: ``skill_member_path("risk", "limits")`` -> ``"skills/risk/rules/limits.md"``.
    """
    return f"{SKILLS_DIR}/{skill_id}/{RULES_DIR}/{rule_id}{suffix}"


def skill_member_location(rel_path: str) -> tuple[str, str] | None:
    """``(skill_id, rule_id)`` of a :func:`skill_member_path` ``.md`` path, else None.

    Example: ``skill_member_location("skills/risk/rules/limits.md")`` -> ``("risk", "limits")``.
    """
    parts = PurePosixPath(rel_path).parts
    if len(parts) != 4 or (parts[0], parts[2]) != (SKILLS_DIR, RULES_DIR):
        return None
    if not parts[3].endswith(".md"):
        return None
    return parts[1], parts[3].removesuffix(".md")


@dataclass(frozen=True)
class MemberReference:
    """One active member rule of a skill, rendered as ``rules/<rule_id>.md``.

    ``text`` is the whole file, identical in every skill root. ``name`` labels the
    member in its skill's Covers clause and index, ``description`` is its index
    line, ``globs`` feed the rule file's first line and ``source_package`` its
    lockfile provenance.

    Example: ``MemberReference("python-typing", ...).filename`` -> ``"python-typing.md"``.
    """

    rule_id: str
    name: str
    description: str
    priority: int
    globs: tuple[str, ...]
    text: str
    source_package: str

    @property
    def filename(self) -> str:
        """The file name under ``rules/``: ``<rule_id>.md``.

        Example: ``member.filename`` -> ``"pytest.md"`` for rule ``pytest``.
        """
        return f"{self.rule_id}.md"

    def to_dict(self) -> dict[str, Any]:
        """Lossless dict form (``globs`` as a list), the inverse of :meth:`from_dict`.

        Example: ``member.to_dict()["globs"]`` -> ``["**/*.py"]``.
        """
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "globs": list(self.globs),
            "text": self.text,
            "source_package": self.source_package,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MemberReference:
        """Inverse of :meth:`to_dict`: ``MemberReference.from_dict(m.to_dict()) == m``."""
        return cls(
            rule_id=data["rule_id"],
            name=data["name"],
            description=data["description"],
            priority=data["priority"],
            globs=tuple(data["globs"]),
            text=data["text"],
            source_package=data["source_package"],
        )
