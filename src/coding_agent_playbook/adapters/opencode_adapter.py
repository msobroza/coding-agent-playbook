"""OpenCode adapter. See SPEC.md §10.6.

OpenCode reads ``AGENTS.md`` natively for rules (walking up the directory
tree, with ``CLAUDE.md`` as fallback) and ``.claude/skills/<id>/SKILL.md``
natively for skills. The OpenCode adapter therefore writes only
``.opencode/command/`` files for prompts — rules and skills are routed
through sibling adapters (AGENTS.md and Claude Code respectively).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import render_for

if TYPE_CHECKING:
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
        """Return ``[]`` — OpenCode reads ``AGENTS.md`` natively.

        Rules are emitted by the AGENTS.md adapter at the repo root, which
        OpenCode picks up by walking up the directory tree (with
        ``CLAUDE.md`` as a documented fallback). Duplicating them here would
        only create drift, so this method is intentionally a no-op.
        """
        del rule, repo_root
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a single OpenCode slash command to ``.opencode/command/<slash>.md``.

        The body is shaped by :func:`render_for` using the
        ``prompt_opencode_command`` format, which:

        * emits the YAML envelope ``---\\ndescription: ...\\n---``,
        * replaces ``{{ var }}`` placeholders for each ``input_variables``
          entry with ``$ARGUMENTS`` (single variable) or ``$1`` / ``$2`` / …
          (multiple variables), and
        * appends an ``includes_rules`` appendix when applicable.

        See SPEC §10.6.1 for the canonical OpenCode command layout and
        SPEC §9.7 for the renderer contract.
        """
        target = repo_root / ".opencode" / "command" / f"{prompt.frontmatter.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_for(
            prompt.source_path or Path("inline"),
            prompt.body,
            "prompt_opencode_command",
            frontmatter=dataclasses.asdict(prompt.frontmatter),
        )
        target.write_text(rendered, encoding="utf-8")
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Return ``[]`` — OpenCode reads ``.claude/skills/`` natively.

        The Claude Code adapter writes the canonical ``.claude/skills/<id>/``
        directory; OpenCode reads it as a fallback per SPEC.md §10.6. Writing
        a parallel copy from this adapter would duplicate content and risk
        the two going out of sync.
        """
        del skill, repo_root
        return []
