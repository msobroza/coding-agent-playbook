"""Claude Code adapter (SPEC §10.3).

Translates canonical ``Rule`` / ``Prompt`` / ``Skill`` artifacts into Claude
Code's native layout:

- Rules are **buffered** during ``write_rule`` and composed into a single
  ``.claude/CLAUDE.md`` during ``finalize`` (priority then ``id`` order).
- Prompts are written immediately to ``.claude/commands/{slash}.md`` as pure
  markdown (no top-level frontmatter — Claude Code commands are plain md).
- Skills are written natively to ``.claude/skills/{id}/`` (``SKILL.md`` plus
  byte-copied ``scripts/`` and ``references/``) through the shared
  :class:`~coding_agent_playbook.adapters._skill_writer.SkillWriter`, so the
  output is byte-identical to the ``opencode`` / ``shared_skills`` skill roots.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters._skill_writer import SkillWriter
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import render_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.renderer import RuleRegistry
    from coding_agent_playbook.types import Prompt, Rule, Skill


class ClaudeCodeAdapter(Adapter):
    """Adapter for Anthropic's Claude Code (``.claude/`` layout).

    The optional ``rule_registry`` is plumbed into :func:`render_for` so the
    ``includes_rules:`` appendix in prompts can be rendered. When the
    orchestrator (PR 10) builds the merged-overlay registry, it passes it in;
    when callers (or tests) omit it, prompts render with no auto-appendix —
    ``includes_rules:`` becomes purely declarative. Mirrors the
    ``ContinueAdapter`` plumbing pattern.
    """

    name = "claude_code"

    #: Native skills root; Claude Code discovers ``.claude/skills/<name>/SKILL.md``.
    _SKILL_WRITER: ClassVar[SkillWriter] = SkillWriter(Path(".claude") / "skills")

    output_locations: ClassVar[tuple[str, ...]] = (
        ".claude/CLAUDE.md",
        ".claude/commands/",
        _SKILL_WRITER.location,
    )

    def __init__(self, *, rule_registry: RuleRegistry | None = None) -> None:
        # Buffer of (priority, rule_id, rendered_section) tuples populated by
        # ``write_rule``. ``finalize`` sorts by (priority, rule_id) and joins.
        self._buffered_rules: list[tuple[int, str, str]] = []
        self._rule_registry = rule_registry

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Buffer a rendered claude_md_section for ``finalize`` to compose.

        Claude Code consumes rules through a single ``.claude/CLAUDE.md`` file
        rather than per-rule files, so this method writes nothing immediately.
        The buffered tuple records (priority, rule_id, rendered_section) so
        ``finalize`` can sort by ``(priority, rule_id)`` for stable output.
        """
        rendered_section = render_for(
            rule.source_path or Path("inline"),
            rule.body,
            "claude_md_section",
            frontmatter=dataclasses.asdict(rule.frontmatter),
        )
        self._buffered_rules.append(
            (rule.frontmatter.priority, rule.frontmatter.id, rendered_section)
        )
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a Claude Code slash-command to ``.claude/commands/{slash}.md``.

        Claude Code commands are pure markdown (no top-level frontmatter
        fence); the ``prompt_claude_command`` renderer handles that shape
        plus optional ``includes_rules`` appendix.
        """
        rendered = render_for(
            prompt.source_path or Path("inline"),
            prompt.body,
            "prompt_claude_command",
            frontmatter=dataclasses.asdict(prompt.frontmatter),
            rule_registry=self._rule_registry,
            template_body=prompt.template_body,
        )
        output_path = repo_root / ".claude" / "commands" / f"{prompt.frontmatter.slash}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        return [output_path]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write a native skill directory under ``.claude/skills/<id>/``.

        Delegates to the shared :class:`SkillWriter` (``SKILL.md`` with
        ``name`` = id and the sentinel as first body line, plus byte-copied
        ``scripts/`` and ``references/``). This adapter does NOT degrade to
        ``Skill.to_prompt`` — siblings without native skill support (e.g.
        Continue) use the ABC default.
        """
        return self._SKILL_WRITER.write(skill, repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        """Compose ``.claude/CLAUDE.md`` from the buffered rule sections.

        Sections are sorted by ``(priority, rule_id)`` for deterministic
        output. Output begins with a one-line sentinel banner followed by a
        generic ``CLAUDE.md`` title block, then each rule section separated by
        the blank lines that ``claude_md_section`` already emits. Returns the
        composed path or ``[]`` if the buffer is empty.
        """
        if not self._buffered_rules:
            return []
        ordered = sorted(self._buffered_rules, key=lambda item: (item[0], item[1]))
        sections = [section for _, _, section in ordered]
        header = (
            f"{sentinel_line('html')}\n"
            "# CLAUDE.md\n\n"
            "This file is generated by coding-agent-playbook.\n\n"
        )
        body = "\n".join(sections)
        output_path = repo_root / ".claude" / "CLAUDE.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(header + body, encoding="utf-8")
        return [output_path]

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """Only ``.claude/commands/`` uses the sentinel scan.

        ``.claude/skills/`` is never scanned: stale skill output is settled by
        ``playbook sync``'s lockfile leftover policy (SPEC §4.2 step 9, §10.8).
        """
        return [repo_root / ".claude" / "commands"]

    def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Generated files that no longer back a current artifact (deletes nothing).

        - ``.claude/commands/``: every sentinel-tagged file not in
          ``written_paths`` (the ABC's sentinel scan).
        - ``.claude/CLAUDE.md``: only if it carries the sentinel and was not
          re-written this sync (``finalize`` skipped it), so a user-authored
          CLAUDE.md is preserved.

        "Sentinel-tagged" is the shared anchored rule (``_sentinel.has_sentinel``
        via :meth:`Adapter._carries_sentinel`). ``.claude/skills/`` is
        deliberately left out: a skill dir mixes engine output with files a user
        may have edited or added, so only the lockfile leftover policy
        (pristine + untracked + listed) may delete there.
        """
        stale = self._stale_by_sentinel(written_paths, repo_root)
        claude_md = repo_root / ".claude" / "CLAUDE.md"
        if (
            claude_md.is_file()
            and claude_md.resolve() not in written_paths
            and self._carries_sentinel(claude_md)
        ):
            stale.append(claude_md)
        return stale
