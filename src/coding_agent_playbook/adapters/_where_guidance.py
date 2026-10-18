"""The ``## Where guidance lives`` map both composite files carry (specs/prS-skills-context.md 6.4.6).

``AGENTS.md`` and the Claude Code rules file hold only always rules; each skill
with active member rules and a ``playbook.files`` phrase becomes one line of a
generated section placed after the always sections. Both adapters buffer it
through :class:`WhereGuidanceBuffer` and render it with the one
:func:`~coding_agent_playbook.skill_document.where_guidance_section`, so the
section is byte-identical in the two files (E10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.skill_document import where_entry, where_guidance_section

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.skill_document import WhereEntry
    from coding_agent_playbook.types import Skill


class WhereGuidanceBuffer:
    """The Where entries of the skills one adapter is handed during a sync.

    Keyed by skill id, so a skill handed over twice is listed once. Example::

        where = WhereGuidanceBuffer()
        where.add(python_coding)  # a skill with members and a files phrase
        where.after(["## Project context\\n...\\n---\\n"])  # [that section, the Where section]
    """

    def __init__(self) -> None:
        self._entries: dict[str, WhereEntry] = {}

    def add(self, skill: Skill) -> None:
        """Buffer ``skill``'s Where entry; a skill without members or ``files`` adds nothing."""
        entry = where_entry(skill)
        if entry is not None:
            self._entries[entry.skill_id] = entry

    def after(self, sections: Sequence[str]) -> list[str]:
        """``sections`` followed by the Where section, or ``sections`` alone without entries."""
        section = where_guidance_section(list(self._entries.values()))
        return [*sections, section] if section else list(sections)
