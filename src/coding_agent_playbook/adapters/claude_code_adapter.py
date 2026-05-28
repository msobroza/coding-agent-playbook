"""Claude Code adapter (SPEC §10.3).

Translates canonical ``Rule`` / ``Prompt`` / ``Skill`` artifacts into Claude
Code's native layout:

- Rules are **buffered** during ``write_rule`` and composed into a single
  ``.claude/CLAUDE.md`` during ``finalize`` (priority then ``id`` order).
- Prompts are written immediately to ``.claude/commands/{slash}.md`` as pure
  markdown (no top-level frontmatter — Claude Code commands are plain md).
- Skills are written natively to ``.claude/skills/{id}/`` including
  ``SKILL.md`` plus optional ``scripts/`` and ``references/`` directories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook.types import Prompt, Rule, Skill


class ClaudeCodeAdapter(Adapter):
    """Adapter for Anthropic's Claude Code (``.claude/`` layout)."""

    name = "claude_code"

    def __init__(self) -> None:
        # Buffer of (priority, rule_id, rendered_section) tuples populated by
        # ``write_rule``. ``finalize`` sorts by (priority, rule_id) and joins.
        self._buffered_rules: list[tuple[int, str, str]] = []

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        raise NotImplementedError

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        raise NotImplementedError

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        raise NotImplementedError

    def finalize(self, repo_root: Path) -> list[Path]:
        raise NotImplementedError

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [
            repo_root / ".claude" / "commands",
            repo_root / ".claude" / "skills",
        ]
