"""OpenCode adapter. See SPEC.md §10.6.

OpenCode reads ``AGENTS.md`` natively for rules (walking up the directory
tree, with ``CLAUDE.md`` as fallback), so rules are routed through the AGENTS.md
adapter. This adapter writes OpenCode's own native outputs:

- prompts -> ``.opencode/command/<slash>.md`` slash commands;
- skills  -> ``.opencode/skills/<id>/`` (``SKILL.md`` + ``scripts/`` +
  ``references/``) through the shared
  :class:`~coding_agent_playbook.adapters._skill_writer.SkillWriter`, so OpenCode
  no longer depends on the ``claude_code`` adapter being enabled for skills.

OpenCode *also* scans ``.claude/skills/`` (Claude-compatibility discovery), so
with ``claude_code`` enabled the same skill is found twice. That is safe:
OpenCode stores discovered skills in a ``Map`` keyed by skill name, last write
wins (anomalyco/opencode ``packages/core/src/config/plugin/compatibility.ts:53``
and ``skill.ts:155``), and both copies are byte-identical.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook.adapters._skill_writer import SkillWriter
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import render_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook._typing import Prompt, Rule, Skill
    from coding_agent_playbook.renderer import RuleRegistry


class OpenCodeAdapter(Adapter):
    """Translate canonical prompts and skills into OpenCode's native layout.

    Rules are an intentional no-op on this adapter: OpenCode picks them up from
    the AGENTS.md adapter's output (``AGENTS.md`` at repo root). See SPEC.md
    §10.6 and §10.6.4 for the OpenCode-touches/does-not-touch matrix.

    The optional ``rule_registry`` is plumbed into :func:`render_for` so the
    ``includes_rules:`` appendix in prompts can be rendered. When the
    orchestrator (PR 10) builds the merged-overlay registry, it passes it in;
    when callers (or tests) omit it, prompts render with no auto-appendix —
    ``includes_rules:`` becomes purely declarative. Mirrors the
    ``ContinueAdapter`` plumbing pattern.
    """

    name = "opencode"

    #: Native skills root; OpenCode discovers ``.opencode/skills/<name>/SKILL.md``.
    _SKILL_WRITER: ClassVar[SkillWriter] = SkillWriter(Path(".opencode") / "skills")

    output_locations: ClassVar[tuple[str, ...]] = (".opencode/command/", _SKILL_WRITER.location)

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
        )
        target.write_text(rendered, encoding="utf-8")
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write a native skill directory under ``.opencode/skills/<id>/``.

        Delegates to the shared :class:`SkillWriter`, so the bytes are
        identical to the ``.claude/skills/`` and ``shared_skills/`` copies.
        Duplicate discovery via ``.claude/skills/`` is safe (see the module
        docstring: OpenCode keys skills by name, last wins).
        """
        return self._SKILL_WRITER.write(skill, repo_root)

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """``.opencode/command/`` is scanned by the ABC's anchored sentinel scan.

        A file is engine output when ``_sentinel.has_sentinel`` finds the
        sentinel line at an anchored position (line 1 for a command file).

        ``.opencode/skills/`` is never scanned: stale skill output is settled by
        ``playbook sync``'s lockfile leftover policy (SPEC §4.2 step 9, §10.8).
        Per SPEC.md §10.6.4, the OpenCode adapter must not touch
        ``.opencode/agent/``, ``.opencode/plugin/``, ``opencode.json``,
        ``AGENTS.md``, or ``.claude/`` — those belong to the user or to
        sibling adapters.
        """
        return [repo_root / ".opencode" / "command"]
