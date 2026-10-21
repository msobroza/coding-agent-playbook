"""The Skill artifact: a skill directory and its member references (SPEC.md §6.3, §6.6.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Imported at run time: Skill.from_dict rebuilds member references from dicts.
from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter


@dataclass
class Skill:
    """A skill directory (SPEC §6.3): ``SKILL.md`` + optional ``scripts/`` and
    ``references/``. Written natively (Agent Skills layout) by the
    ``claude_code`` / ``opencode`` / ``shared_skills`` adapters through the shared
    ``SkillWriter``; other adapters degrade it via :meth:`to_prompt`.
    ``member_references`` are the skill's active member rules, rendered (ADR 0001)."""

    frontmatter: dict[str, Any]
    body: str
    scripts_dir: Path | None
    references_dir: Path | None
    source_package: str
    # Set by compose_skills at sync: the active member rules, rendered.
    member_references: tuple[MemberReference, ...] = ()
    # The skill's source directory, when it was loaded from one: ``playbook
    # validate`` lists its references/ and examples/ files against
    # ``playbook.references`` (prU D47). None for a skill built in memory.
    source_dir: Path | None = None

    def to_prompt(self) -> Prompt:
        """Degrade this Skill to a Prompt.

        ``scripts_dir`` and ``references_dir`` are intentionally *not* carried
        into the Prompt — adapters that natively support skills (e.g.
        :class:`ClaudeCodeAdapter`) handle those side files separately by
        overriding ``write_skill``. For every other adapter the degrade path
        is lossy by design (SPEC §6.3).

        ``Skill.frontmatter`` is an open ``dict[str, Any]`` because the Claude
        Code SKILL.md schema is not strict YAML the way Rule/Prompt frontmatter
        is. We pull canonical fields out with sensible fallbacks so the
        resulting Prompt is always writable.
        """
        identifier = self.frontmatter.get("id", "skill")
        return Prompt(
            frontmatter=PromptFrontmatter(
                id=identifier,
                name=self.frontmatter.get("name", "Skill"),
                description=self.frontmatter.get("description", ""),
                slash=self.frontmatter.get("slash") or identifier,
            ),
            body=self.body,
            template_body=self.body,
            is_templated=False,
            source_path=None,
            source_package=self.source_package,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dict(self.frontmatter),
            "body": self.body,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
            "references_dir": None if self.references_dir is None else str(self.references_dir),
            "source_package": self.source_package,
            "member_references": [member.to_dict() for member in self.member_references],
            "source_dir": None if self.source_dir is None else str(self.source_dir),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        scripts_dir = data["scripts_dir"]
        references_dir = data["references_dir"]
        # A dict written before member references existed has no such key.
        members = data.get("member_references", ())
        source_dir = data.get("source_dir")
        return cls(
            dict(data["frontmatter"]),
            data["body"],
            None if scripts_dir is None else Path(scripts_dir),
            None if references_dir is None else Path(references_dir),
            data["source_package"],
            tuple(MemberReference.from_dict(member) for member in members),
            None if source_dir is None else Path(source_dir),
        )
