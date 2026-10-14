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

import dataclasses
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import SENTINEL, render_for

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
        """Write a Claude Code native skill directory under ``.claude/skills/<id>/``.

        Skills are first-class in Claude Code: the directory contains
        ``SKILL.md`` (frontmatter + body, written as YAML), an optional
        ``scripts/`` directory, and an optional ``references/`` directory.
        This adapter does NOT degrade to ``Skill.to_prompt`` — siblings that
        lack native skill support (e.g. Continue) use the ABC default.
        """
        skill_id = str(skill.frontmatter.get("id", "skill"))
        skill_dir = repo_root / ".claude" / "skills" / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)

        # SKILL.md: standard frontmatter + body. We don't run a renderer here —
        # the skill's frontmatter is dict[str, Any] (not a dataclass like
        # Rule/Prompt) and Claude Code reads it as-is.
        fenced = yaml.safe_dump(
            dict(skill.frontmatter), sort_keys=False, allow_unicode=True
        ).rstrip("\n")
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(f"---\n{fenced}\n---\n{skill.body}", encoding="utf-8")
        written: list[Path] = [skill_md]

        if skill.scripts_dir is not None and skill.scripts_dir.is_dir():
            written.extend(self._copy_tree(skill.scripts_dir, skill_dir / "scripts"))
        if skill.references_dir is not None and skill.references_dir.is_dir():
            written.extend(self._copy_tree(skill.references_dir, skill_dir / "references"))
        return written

    @staticmethod
    def _copy_tree(src: Path, dst: Path) -> list[Path]:
        """Copy ``src`` -> ``dst`` recursively and return the list of files written.

        Uses :func:`shutil.copytree` with ``dirs_exist_ok=True`` so a re-sync
        overwrites the previous output. The returned paths are the leaf files
        actually copied (directories are excluded so the cleanup scan sees
        files only).
        """
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return [path for path in dst.rglob("*") if path.is_file()]

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
            f"<!-- {SENTINEL} -->\n"
            "# CLAUDE.md\n\n"
            "This file is generated by coding-agent-playbook.\n\n"
        )
        body = "\n".join(sections)
        output_path = repo_root / ".claude" / "CLAUDE.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(header + body, encoding="utf-8")
        return [output_path]

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [
            repo_root / ".claude" / "commands",
            repo_root / ".claude" / "skills",
        ]

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Remove generated files that no longer back a current artifact.

        Three output kinds need cleanup:

        - ``.claude/commands/`` and ``.claude/skills/`` are directories — every
          file with a leading sentinel marker that isn't in ``written_paths``
          is deleted.
        - ``.claude/CLAUDE.md`` is a single file. If it isn't in
          ``written_paths`` (i.e. the buffer was empty so ``finalize`` skipped
          it) AND it carries the sentinel, delete it; otherwise leave it alone
          so a user-authored CLAUDE.md is preserved.

        Each guard mirrors the ABC's default scan algorithm (Track 6 lands a
        shared ``_default_cleanup`` on the ABC; this override exists because
        Claude Code uniquely needs the single-file CLAUDE.md branch).
        """
        deleted: list[Path] = []
        deleted.extend(self._scan_for_stale(written_paths, repo_root))
        claude_md = repo_root / ".claude" / "CLAUDE.md"
        if claude_md.is_file() and claude_md.resolve() not in written_paths:
            try:
                first_line = claude_md.read_text(encoding="utf-8").split("\n", 1)[0]
            except (UnicodeDecodeError, OSError):
                return deleted
            if SENTINEL in first_line:
                claude_md.unlink()
                deleted.append(claude_md)
        return deleted

    def _scan_for_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Walk each output directory and delete sentinel-tagged files not in
        ``written_paths``. Files without the sentinel (user-authored) are
        preserved; binary files (UnicodeDecodeError) are skipped.
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
