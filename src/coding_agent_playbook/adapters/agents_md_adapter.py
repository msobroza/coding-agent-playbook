"""AGENTS.md adapter. See SPEC.md §10.4.

Composes a single ``AGENTS.md`` file at the repo root from buffered rule
sections. Prompts and skills are no-ops: AGENTS.md is rules-only.

This adapter always runs regardless of which other adapters are enabled (the
orchestrator enforces that invariant — the adapter itself just buffers rules
and finalizes the file).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule, Skill


class AgentsMdAdapter(Adapter):
    """Translate canonical rules into a single ``AGENTS.md`` at repo root."""

    name = "agents_md"

    def __init__(self) -> None:
        # (priority, rule_id, rendered_section) — sorted at finalize time so
        # buffer-order doesn't matter to callers.
        self._buffered_rules: list[tuple[int, str, str]] = []

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:  # noqa: ARG002
        raise NotImplementedError("lands in Task 8.2")

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:  # noqa: ARG002
        raise NotImplementedError("lands in Task 8.2")

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:  # noqa: ARG002
        raise NotImplementedError("lands in Task 8.2")
