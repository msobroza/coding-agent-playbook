"""AGENTS.md adapter. See SPEC.md §10.4.

Composes a single ``AGENTS.md`` file at the repo root from buffered rule
sections. Prompts and skills are no-ops: AGENTS.md is rules-only.

This adapter always runs regardless of which other adapters are enabled (the
orchestrator enforces that invariant — the adapter itself just buffers rules
and finalizes the file).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import render_for

if TYPE_CHECKING:
    from coding_agent_playbook._typing import Prompt, Rule, Skill


class AgentsMdAdapter(Adapter):
    """Translate canonical rules into a single ``AGENTS.md`` at repo root.

    Rules-only by design: prompts and skills route through other adapters
    (Continue / Claude Code) — AGENTS.md is the universal "rules" surface
    every coding assistant agrees to read.
    """

    name = "agents_md"

    def __init__(self) -> None:
        # (priority, rule_id, rendered_section). Buffered now, sorted and
        # written at finalize() time so the on-disk order is stable across
        # syncs regardless of the orchestrator's iteration order.
        self._buffered_rules: list[tuple[int, str, str]] = []

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:  # noqa: ARG002
        """Render a rule to the shared markdown-section format and buffer it.

        Returns ``[]``: nothing is written until ``finalize`` composes the
        single ``AGENTS.md`` file.
        """
        rendered = render_for(
            rule.source_path or Path("inline"),
            rule.body,
            "agents_md_section",
            frontmatter=rule.frontmatter.__dict__,
        )
        self._buffered_rules.append(
            (rule.frontmatter.priority, rule.frontmatter.id, rendered)
        )
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:  # noqa: ARG002
        """No-op: AGENTS.md is rules-only.

        Prompts are emitted by harness-specific adapters (Continue, Claude
        Code, OpenCode). The orchestrator passes every prompt to every
        adapter; this one declines.
        """
        return []

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:  # noqa: ARG002
        """No-op: AGENTS.md is rules-only.

        Native skill emission belongs to the Claude Code adapter; OpenCode
        reads ``.claude/skills/`` directly. This adapter never degrades a
        skill to a prompt either (the default Adapter degrade path), since
        prompts are also no-ops here.
        """
        return []
