"""The catalog-only ``playbook:`` block of a skill and its one accessor (E1, E6).

A leaf of the skills package: ``skills.document`` renders from the block,
``skills.sections`` parses its ``sections`` list, and the document renders the
sectioned index from those sections, so both read the block from here instead
of from each other (which would be an import cycle).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.skill import Skill

#: The catalog-only frontmatter key of a skill with member rules; stripped on output (E1).
PLAYBOOK_BLOCK_KEY: Final = "playbook"


def playbook_block(skill: Skill) -> Mapping[str, Any]:
    """The raw ``playbook:`` block of ``skill``; ``{}`` when absent or not a mapping.

    The one accessor of the block: V7 reports a non-mapping block, every reader
    sees it as empty. Values stay raw YAML (``Any``) for the callers to check.

    Example: ``playbook_block(python_coding).get("use_when")`` -> ``"editing Python code"``.
    """
    block = skill.frontmatter.get(PLAYBOOK_BLOCK_KEY)
    return block if isinstance(block, Mapping) else {}
