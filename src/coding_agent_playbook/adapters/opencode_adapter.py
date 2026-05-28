"""OpenCode adapter. See SPEC.md §10.6.

OpenCode reads ``AGENTS.md`` natively for rules (walking up the directory
tree, with ``CLAUDE.md`` as fallback) and ``.claude/skills/<id>/SKILL.md``
natively for skills. The OpenCode adapter therefore writes only
``.opencode/command/`` files for prompts — rules and skills are routed
through sibling adapters (AGENTS.md and Claude Code respectively).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule, Skill


class OpenCodeAdapter(Adapter):
    """Translate canonical prompts into OpenCode slash-command files.

    Rules and skills are intentional no-ops on this adapter: OpenCode picks
    them up from the AGENTS.md adapter's output (``AGENTS.md`` at repo root)
    and the Claude Code adapter's output (``.claude/skills/``). See
    SPEC.md §10.6 and §10.6.4 for the OpenCode-touches/does-not-touch matrix.
    """

    name = "opencode"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Skeleton — implementation lands with Task 9.2."""
        raise NotImplementedError("OpenCodeAdapter.write_rule lands with Task 9.2")

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Skeleton — implementation lands with Task 9.3."""
        raise NotImplementedError("OpenCodeAdapter.write_prompt lands with Task 9.3")

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Skeleton — implementation lands with Task 9.2."""
        raise NotImplementedError("OpenCodeAdapter.write_skill lands with Task 9.2")
