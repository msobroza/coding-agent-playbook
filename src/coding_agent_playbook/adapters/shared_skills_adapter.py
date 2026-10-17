"""Shared-skills adapter. See SPEC.md §10.8.

Emits every canonical skill as a native Agent-Skills directory under
``<repo>/shared_skills/<id>/`` — the **cross-agent skills hub**: one
agent-neutral, committed copy of the skills that any Agent-Skills-aware tool
(or a human) can be pointed at, independent of which harness adapters are on.

Rules and prompts are no-ops here: rules reach every assistant through
``AGENTS.md`` and prompts through the harness adapters. The skill bytes come
from the shared :class:`~coding_agent_playbook.adapters._skill_writer.SkillWriter`
and are identical to the ``.claude/skills/`` and ``.opencode/skills/`` copies.

On by default (``playbook init`` lists it in ``adapters_enabled``) but **not**
force-enabled like ``agents_md`` — remove it from the top-level
``adapters_enabled`` list to opt out.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook.adapters._skill_writer import SkillWriter
from coding_agent_playbook.adapters.base import Adapter

if TYPE_CHECKING:
    from coding_agent_playbook._typing import Prompt, Rule, Skill

#: Repo-relative root of the cross-agent skills hub.
SHARED_SKILLS_ROOT = Path("shared_skills")


class SharedSkillsAdapter(Adapter):
    """Write canonical skills to ``shared_skills/<id>/``; ignore rules and prompts.

    Registered under ``coding_agent_playbook.adapters`` as ``shared_skills``.
    Takes no ``rule_registry`` (it renders no prompts), so
    :func:`~coding_agent_playbook.orchestrator.discover_adapters` constructs it
    with no arguments, exactly like ``agents_md``.

    Example::

        adapter = SharedSkillsAdapter()
        adapter.write_skill(skill, repo_root)  # -> [repo_root/"shared_skills"/<id>/"SKILL.md", ...]
    """

    name = "shared_skills"

    _SKILL_WRITER: ClassVar[SkillWriter] = SkillWriter(SHARED_SKILLS_ROOT)
    native_skills_root: ClassVar[str | None] = _SKILL_WRITER.root.as_posix()

    output_locations: ClassVar[tuple[str, ...]] = (_SKILL_WRITER.location,)

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Return ``[]`` — rules reach every assistant through ``AGENTS.md``."""
        del rule, repo_root
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Return ``[]`` — prompts are emitted by the harness adapters."""
        del prompt, repo_root
        return []

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write ``shared_skills/<id>/`` via the shared :class:`SkillWriter`.

        No ``cleanup_stale`` override (the ABC default scans nothing): a removed
        skill's dir is settled by ``playbook sync``'s lockfile leftover policy.
        """
        return self._SKILL_WRITER.write(skill, repo_root)
