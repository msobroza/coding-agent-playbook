"""A member rule as its skill delivers it: one ``references/<rule-id>.md`` file.

A scoped rule that names a skill in ``skill:`` is a member rule of that skill
(ADR 0001). At sync, ``skill_membership.compose_skills`` renders each active
member into a :class:`MemberReference` and attaches them to
``Skill.member_references``; the skill writer then writes ``text`` under every
skill root, so the copies are byte-identical.

A stdlib-only leaf: ``types`` imports it at run time for ``Skill.from_dict``,
so it cannot import ``types`` back (specs/prS-skills-context.md section 6.4.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The directory inside a skill that holds its references (Agent Skills layout).
_REFERENCES_DIR = "references"


def member_reference_path(rule_id: str) -> str:
    """Where a member rule lives inside its skill directory (E16).

    The one spelling the writer, the lockfile split and prompt pointer lines share.

    Example: ``member_reference_path("pytest")`` -> ``"references/pytest.md"``.
    """
    return f"{_REFERENCES_DIR}/{rule_id}.md"


@dataclass(frozen=True)
class MemberReference:
    """One active member rule of a skill, rendered as ``references/<rule_id>.md``.

    ``text`` is the whole file, identical in every skill root. ``name`` labels the
    member in its skill's Covers clause and index, ``description`` is its index
    line, ``globs`` feed the reference's first line and ``source_package`` its
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
        """The file name under ``references/``: ``<rule_id>.md``.

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
