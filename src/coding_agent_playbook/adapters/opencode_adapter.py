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
from coding_agent_playbook.renderer import SENTINEL, render_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook._typing import Prompt, Rule, Skill
    from coding_agent_playbook.renderer import RuleRegistry


class OpenCodeAdapter(Adapter):
    """Translate canonical prompts into OpenCode slash-command files.

    Rules and skills are intentional no-ops on this adapter: OpenCode picks
    them up from the AGENTS.md adapter's output (``AGENTS.md`` at repo root)
    and the Claude Code adapter's output (``.claude/skills/``). See
    SPEC.md §10.6 and §10.6.4 for the OpenCode-touches/does-not-touch matrix.

    The optional ``rule_registry`` is plumbed into :func:`render_for` so the
    ``includes_rules:`` appendix in prompts can be rendered. When the
    orchestrator (PR 10) builds the merged-overlay registry, it passes it in;
    when callers (or tests) omit it, prompts render with no auto-appendix —
    ``includes_rules:`` becomes purely declarative. Mirrors the
    ``ContinueAdapter`` plumbing pattern.
    """

    name = "opencode"

    def __init__(self, *, rule_registry: RuleRegistry | None = None) -> None:
        self._rule_registry = rule_registry

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
            rule_registry=self._rule_registry,
            template_body=prompt.template_body,
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

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """Only ``.opencode/command/`` is owned by this adapter.

        Per SPEC.md §10.6.4, the OpenCode adapter must not touch
        ``.opencode/agent/``, ``.opencode/plugin/``, ``opencode.json``,
        ``AGENTS.md``, or ``.claude/`` — those belong to the user or to
        sibling adapters.
        """
        return [repo_root / ".opencode" / "command"]

    def _default_cleanup(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Scan each ``_output_directories(repo_root)`` entry and delete any
        sentinel-tagged file whose absolute path is not in ``written_paths``.

        This matches the algorithm Track 6 lands on the ABC; the override is
        kept on the OpenCode adapter so this track can self-verify cleanly
        before Track 6 merges. After integration the inherited behaviour is
        byte-identical, so the override is a safe no-op.
        """
        deleted: list[Path] = []
        for output_dir in self._output_directories(repo_root):
            if not output_dir.is_dir():
                continue
            for path in output_dir.rglob("*"):
                if not path.is_file():
                    continue
                if path.resolve() in written_paths:
                    continue
                try:
                    first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
                except (UnicodeDecodeError, OSError):
                    continue
                if SENTINEL in first_line:
                    path.unlink()
                    deleted.append(path)
        return deleted
